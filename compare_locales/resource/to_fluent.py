from __future__ import annotations

import re
from typing import List, Tuple, Union

from fluent.syntax import ast as Fluent
from .elements import (
    CatchallKey,
    Expression,
    FunctionRef,
    Literal,
    Message,
    Pattern,
    PatternMessage,
    SelectMessage,
    Text,
    VariableRef,
    VariantKey,
)

_re_identifier = re.compile(r"^[a-zA-Z][\w-]*$")
_re_number_literal = re.compile(r"^-?[0-9]+(\.[0-9]+)?$")
_re_message_id = re.compile(r"^(-?[a-zA-Z][\w-]*)(?:\.([a-zA-Z][\w-]*))?$")


def to_fluent(entries: List[Message]) -> Fluent.Resource:
    res = Fluent.Resource()
    fmsg: Union[Fluent.Message, Fluent.Term, None] = None
    prev_key0 = None
    for msg in entries:
        fb = FluentBuilder(msg)
        value = (
            fb.pattern(msg.value.pattern)
            if isinstance(msg.value, PatternMessage)
            else fb.select(msg.value)
        )
        key0 = msg.key[0]
        is_attr = len(msg.key) > 1
        comment = Fluent.Comment("\n".join(msg.comments)) if msg.comments else None
        if is_attr and fmsg and key0 == prev_key0:
            if comment:
                raise Exception(f"Unsupported comment on {msg.key}")
            attr_name = Fluent.Identifier(msg.key[1])
            attr = Fluent.Attribute(attr_name, value)
            fmsg.attributes.append(attr)
        else:
            if key0[0] == "-":
                if is_attr:
                    raise Exception(f"Value missing for term {key0}")
                id = Fluent.Identifier(key0[1:])
                fmsg = Fluent.Term(id, value, comment=comment)
            else:
                id = Fluent.Identifier(key0)
                if is_attr:
                    attr_name = Fluent.Identifier(msg.key[1])
                    attr = Fluent.Attribute(attr_name, value)
                    fmsg = Fluent.Message(id, attributes=[attr], comment=comment)
                else:
                    fmsg = Fluent.Message(id, value=value, comment=comment)
            res.body.append(fmsg)
            prev_key0 = key0
    return res


class FluentBuilder:
    def __init__(self, msg: Message):
        self._declarations = msg.value.declarations
        self.__default_key = None

    def select(self, msg: SelectMessage) -> Fluent.Pattern:
        """
        Map a SelectMessage to a corresponding Fluent pattern,
        with nested selectors if necessary.

        For multi-selector messages, variants are expected to be grouped
        from the leftmost selector onwards.
        """

        # This gets a bit complicated. To figure out what's going on,
        # let's presume we're starting with a two-selector message:
        #   .match $foo :number
        #   .match $bar :number
        #   .when 0 one {{None, One}}
        #   .when 0 * {{None, Other}}
        #   .when * * {{Any}}

        # First we build a mutable `variants` list to work with:
        #   [
        #     ([Literal('0'), Literal('one')], Fluent.Pattern('None, One')),
        #     ([Literal('0'), CatchallKey()], Fluent.Pattern('None, Other')),
        #     ([CatchallKey(), CatchallKey()], Fluent.Pattern('Any')),
        #   ]
        variants: List[Tuple[List[VariantKey], Fluent.Pattern]] = []
        for keys, value in msg.variants:
            pattern = self.pattern(value)
            variants.append((keys.copy(), pattern))

        # We'll be collapsing the list of variants until only the first one is left,
        # with an empty list of keys.
        k0 = variants[0][0]
        while k0:
            # Starting from the last selector.
            # With the example, we'll be here twice:
            # 1. sel = Fluent('NUMBER($bar)')
            # 2. sel = Fluent('NUMBER($foo)')
            sel = self._expression(msg.selectors[len(k0) - 1])

            # These track the current Fluent select expression to which we may be adding the current variant,
            # as well as the variant keys corresponding to that select expression.
            fsel = None
            baseKeys = []

            # We'll need to modify the list while iterating,
            # so we can't loop pythonically.
            i = 0
            while i < len(variants):
                keys, pattern = variants[i]
                # On the first NUMBER($bar) loop, we'll have:
                #   1. baseKeys = [],
                #      keys = [Literal('0')],
                #      variant = Fluent('[one] None, One')
                #   2. baseKeys = [Literal('0')],
                #      keys = [Literal('0')],
                #      variant = Fluent('*[other] None, Other')
                #   3. baseKeys = [Literal('0')],
                #      keys = [CatchallKey()],
                #      variant = Fluent('*[other] Any')
                # On the second NUMBER($foo) loop, this will be:
                #   1. baseKeys = [],
                #      keys = [],
                #      variant = Fluent('[0] { NUMBER($bar) ->\n [one] None, One\n *[other] None, Other }'))
                #   2. baseKeys = [],
                #      keys = [],
                #      variant = Fluent('*[other] { NUMBER($bar) ->\n *[other] Any }')
                key = keys.pop()
                variant = Fluent.Variant(
                    self._variant_key(key, msg.variants),
                    pattern,
                    default=isinstance(key, CatchallKey),
                )
                if fsel and keys == baseKeys:
                    # If the keys of the current variant (excluding the last, which is popped above)
                    # match those used for the current select expression,
                    # we add the variant to that select expression and remove it from the list.
                    fsel.variants.append(variant)
                    variants.pop(i)
                    i -= 1
                else:
                    # If the keys don't match, we create a new select expression.
                    baseKeys = keys
                    fsel = Fluent.SelectExpression(sel.clone(), [variant])
                    variants[i] = (keys, Fluent.Pattern([Fluent.Placeable(fsel)]))
                i += 1
        # After the first NUMBER($bar) loop, the `variants` will be:
        #   [
        #     ([Literal('0')], Fluent('[0] { NUMBER($bar) ->\n [one] None, One\n *[other] None, Other }')),
        #     ([CatchallKey()], Fluent('*[other] { NUMBER($bar) ->\n *[other] Any }')),
        #   ]
        # After the second NUMBER($foo) loop, the `variants` will be:
        #   [
        #     ([], Fluent('{ NUMBER($foo) ->
        #                      [0]
        #                          { NUMBER($bar) ->
        #                              [one] None, One
        #                             *[other] None, Other
        #                          }
        #                     *[other]
        #                          { NUMBER($bar) ->
        #                             *[other] Any
        #                          }
        #                  }')),
        #   ]
        if len(variants) != 1:
            raise Exception(
                f"Error resolving select message variants (n={len(variants)})"
            )

        # Finally, let's clean up any selectors with only one variant
        # so we end up with the final result:
        #   { NUMBER($foo) ->
        #       [0]
        #           { NUMBER($bar) ->
        #               [one] None, One
        #              *[other] None, Other
        #           }
        #      *[other] Any
        #   }
        def prune_variants(pattern: Fluent.Pattern):
            if len(pattern.elements) == 1:
                el0 = pattern.elements[0]
                if isinstance(el0, Fluent.Placeable) and isinstance(
                    el0.expression, Fluent.SelectExpression
                ):
                    variants = el0.expression.variants
                    for var in variants:
                        prune_variants(var.value)
                    if len(variants) == 1:
                        pattern.elements = variants[0].value.elements
            return pattern

        return prune_variants(variants[0][1])

    def pattern(self, pattern: Pattern) -> Fluent.Pattern:
        elements = [
            Fluent.TextElement(el.value)
            if isinstance(el, Text)
            else Fluent.Placeable(self._expression(el))
            for el in pattern
        ]
        return Fluent.Pattern(elements)

    def _expression(self, exp: Expression) -> Fluent.InlineExpression:
        if isinstance(exp, VariableRef):
            return self._variable(exp.name)
        elif isinstance(exp, FunctionRef):
            return self._function(exp)
        else:
            return Fluent.StringLiteral(exp.value)

    def _variable(self, name: str) -> Fluent.InlineExpression:
        decl = self._declarations.get(name)
        return (
            self._expression(decl)
            if decl
            else Fluent.VariableReference(Fluent.Identifier(name))
        )

    def _function(self, fn: FunctionRef):
        def named_arg(name: str, value: Union[Literal, VariableRef]):
            id = Fluent.Identifier(name)
            fv = self._value(value)
            if isinstance(fv, Fluent.Literal):
                return Fluent.NamedArgument(id, fv)
            raise Exception(
                f"Fluent options must have literal values (got {fv} for {name})"
            )

        arg0 = self._value(fn.operand) if fn.operand else None
        args = Fluent.CallArguments(
            positional=[arg0] if arg0 else None,
            named=[named_arg(name, value) for name, value in fn.options.items()]
            if fn.options
            else None,
        )
        id = fn.name
        if id == "datetime":
            id = "DATETIME"
        elif id == "number":
            if isinstance(arg0, Fluent.NumberLiteral) and not args.named:
                return arg0
            else:
                id = "NUMBER"
        elif id == "message":
            if not isinstance(arg0, Fluent.StringLiteral):
                raise Exception(f"Invalid message identifier type: {arg0}")
            match = _re_message_id.match(arg0.value)
            if not match:
                raise Exception(f"Invalid message identifier: {arg0.value}")
            msgId = match.group(1)
            msgAttr = match.group(2)
            attr = Fluent.Identifier(msgAttr) if msgAttr else None
            if msgId[0] == "-":
                args.positional = []
                return Fluent.TermReference(
                    Fluent.Identifier(msgId[1:]),
                    attribute=attr,
                    arguments=args if args.named else None,
                )
            if args.named:
                raise Exception("Options are not allowed for Fluent message references")
            return Fluent.MessageReference(Fluent.Identifier(msgId), attr)
        return Fluent.FunctionReference(Fluent.Identifier(id), args)

    def _value(self, value: Union[Literal, VariableRef]) -> Fluent.InlineExpression:
        if isinstance(value, Literal):
            if _re_number_literal.match(value.value):
                return Fluent.NumberLiteral(value.value)
            else:
                return Fluent.StringLiteral(value.value)
        else:
            return self._variable(value.name)

    def _variant_key(
        self, key: VariantKey, variants: List[Tuple[List[VariantKey], Pattern]]
    ) -> Union[Fluent.Identifier, Fluent.NumberLiteral]:
        if isinstance(key, CatchallKey):
            kv = key.value or self._variant_default_key(variants)
        else:
            kv = key.value
        if _re_number_literal.match(kv):
            return Fluent.NumberLiteral(kv)
        if _re_identifier.match(kv):
            return Fluent.Identifier(kv)
        raise Exception(f"Invalid variant key for Fluent: {kv}")

    def _variant_default_key(
        self, variants: List[Tuple[List[VariantKey], Pattern]]
    ) -> str:
        if self.__default_key:
            return self.__default_key
        dk = "other"
        all_keys = (key for var in variants for key in var[0])
        if any(
            key for key in all_keys if isinstance(key, CatchallKey) and not key.value
        ):
            i = 0
            while any(
                key
                for key in all_keys
                if isinstance(key, Literal) and key.value == self.__default_key
            ):
                i += 1
                self.__default_key = f"other{i}"
        self.__default_key = dk
        return dk
