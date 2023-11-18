from __future__ import annotations

from collections import OrderedDict
from typing import Iterator, List, Optional, Tuple, Union

from fluent.syntax import ast as Fluent

from .elements import (
    CatchallKey,
    Expression,
    FunctionRef,
    Literal,
    Message,
    OptionValue,
    Pattern,
    PatternMessage,
    SelectMessage,
    Text,
    VariableRef,
    VariantKey,
)
from .errors import ParseError


class SelectArg:
    def __init__(self, sel: Fluent.SelectExpression) -> None:
        self.defaultName = ""
        self.selector = sel.selector

        def name(v: Fluent.Variant) -> Union[str, None]:
            name = v.key.name if isinstance(v.key, Fluent.Identifier) else v.key.value
            if v.default:
                self.defaultName = str(name)
                return None
            else:
                return name

        self.keys: List[Union[str, int, None]] = list(map(name, sel.variants))


def select_args(pattern: Fluent.Pattern) -> List[SelectArg]:
    args: List[SelectArg] = []

    def add(arg: SelectArg) -> None:
        prev = next((a for a in args if a.selector.equals(arg.selector)), None)
        if prev:
            prev.keys += arg.keys
        else:
            args.append(arg)

    for el in pattern.elements:
        if isinstance(el, Fluent.Placeable) and isinstance(
            el.expression, Fluent.SelectExpression
        ):
            add(SelectArg(el.expression))
            for v in el.expression.variants:
                for arg in select_args(v.value):
                    add(arg)
    return args


def options(args: Optional[Fluent.CallArguments]) -> OrderedDict[str, OptionValue]:
    options: OrderedDict[str, OptionValue] = OrderedDict()
    if args:
        for arg in args.named:
            options[arg.name.name] = (
                Literal(False, arg.value.value)
                if isinstance(arg.value, Fluent.NumberLiteral)
                else Literal(True, arg.value.parse()["value"])
            )
    return options


def expression_part(exp: Union[Fluent.Expression, Fluent.Placeable]) -> Expression:
    if isinstance(exp, Fluent.NumberLiteral):
        return FunctionRef("number", Literal(False, exp.value))
    elif isinstance(exp, Fluent.StringLiteral):
        return Literal(True, exp.parse()["value"])
    elif isinstance(exp, Fluent.VariableReference):
        return VariableRef(exp.id.name)
    elif isinstance(exp, Fluent.FunctionReference):
        args = [expression_part(exp) for exp in exp.arguments.positional]
        if len(args) > 1:
            raise ParseError("More than one positional argument is not supported.")
        name = exp.id.name
        if name == "NUMBER":
            name = "number"
        elif name == "DATETIME":
            name = "datetime"
        operand = args[0]
        if isinstance(operand, FunctionRef):
            raise ParseError("A Fluent function is not supported here.")
        options_ = options(exp.arguments)
        return FunctionRef(name, operand, options_)
    elif isinstance(exp, Fluent.MessageReference):
        msgId = (
            f"${exp.id.name}.${exp.attribute.name}" if exp.attribute else exp.id.name
        )
        return FunctionRef("message", Literal(False, msgId))
    elif isinstance(exp, Fluent.TermReference):
        msgId = (
            "-${exp.id.name}.${exp.attribute.name}"
            if exp.attribute
            else f"-${exp.id.name}"
        )
        operand = Literal(False, msgId)
        options_ = options(exp.arguments)
        return FunctionRef("message", operand, options_)
    elif isinstance(exp, Fluent.Placeable):
        return expression_part(exp.expression)
    raise ParseError(f"${exp.__class__.__name__} not supported here")


def element_part(el: Union[Fluent.TextElement, Fluent.Placeable]) -> Expression | Text:
    if isinstance(el, Fluent.TextElement):
        return Text(el.value)
    else:
        return expression_part(el.expression)


def fluent_select(
    el: Union[Fluent.TextElement, Fluent.Placeable]
) -> Optional[Fluent.SelectExpression]:
    if isinstance(el, Fluent.TextElement):
        return None
    elif isinstance(el.expression, Fluent.SelectExpression):
        return el.expression
    elif isinstance(el.expression, Fluent.Placeable):
        return fluent_select(el.expression)
    else:
        return None


def message(ast: Fluent.Pattern) -> Union[PatternMessage, SelectMessage]:
    """
    Compile a Fluent.Pattern (i.e. the value of a Fluent message or an attribute)
    into a Message data object.
    """
    args = select_args(ast)
    if len(args) == 0:
        return PatternMessage([element_part(el) for el in ast.elements])

    # First determine the keys for all variants, with empty values.
    # Fluent supports selectors within a message,
    # while our data model supports top-level selectors only.
    # Mapping between these approaches gets a bit complicated
    # when a message contains more than one selector.
    keys: List[List[Union[str, int, None]]] = []
    for i, arg in enumerate(args):
        kk: List[Union[str, int, None]] = []
        for key in arg.keys:
            if key not in kk:
                kk.append(key)
        kk.sort(key=lambda key: 1 if key is None else -1 if isinstance(key, int) else 0)
        if i == 0:
            keys = [[key] for key in kk]
        else:
            # For selectors after the first,
            # replace each previous variant with len(kk) variants,
            # one for each of this selector's keys.
            for j in range(len(keys), 0, -1):
                prev = keys[j - 1]
                keys[j - 1 : j] = [prev + [key] for key in kk]

    variants: List[Tuple[List[VariantKey], Pattern]] = [
        (
            [
                CatchallKey(args[i].defaultName)
                if k is None
                else Literal(False, str(k))
                for i, k in enumerate(key)
            ],
            [],
        )
        for key in keys
    ]

    def addParts(
        pattern: Fluent.Pattern,
        filter: List[Tuple[int, Optional[str]]],  # [(idx, value)]
    ):
        """
        This reads `args` and modifies `variants`

        @param filter - Selects which cases we're adding to
        """
        for el in pattern.elements:
            sel = fluent_select(el)
            if sel:
                idx = next(
                    (i for (i, a) in enumerate(args) if a.selector.equals(sel.selector))
                )
                for v in sel.variants:
                    value = (
                        None
                        if v.default
                        else v.key.name
                        if isinstance(v.key, Fluent.Identifier)
                        else v.key.value
                    )
                    addParts(v.value, filter + [(idx, value)])
            else:
                for vk, vp in variants:
                    if all(
                        value is None
                        if isinstance(key, CatchallKey)
                        else value == key.value
                        for key, value in map(lambda f: (vk[f[0]], f[1]), filter)
                    ):
                        last = vp[-1] if len(vp) else None
                        part = element_part(el)
                        if isinstance(last, Text) and isinstance(part, Text):
                            last.value += part.value
                        else:
                            vp.append(part)

    addParts(ast, [])

    return SelectMessage([expression_part(arg.selector) for arg in args], variants)


def messages(fe: Fluent.EntryType, groupcomments: List[str]) -> Iterator[Message]:
    if not fe.span:
        raise ParseError("Fluent parser must include spans in output")
    if isinstance(fe, Fluent.Message):
        id = fe.id.name
        comments = groupcomments + (
            fe.comment.content.split("\n") if fe.comment and fe.comment.content else []
        )
        if fe.value:
            value = message(fe.value)
            ispan = fe.id.span or fe.span
            vspan = fe.value.span or fe.span
            yield Message((id,), value, (ispan.start, vspan.end), comments)
            if comments:
                comments = None
        for attr in fe.attributes:
            value = message(attr.value)
            span = attr.span or fe.span
            yield Message((id, attr.id.name), value, (span.start, span.end), comments)
            if comments:
                comments = None
    elif isinstance(fe, Fluent.Term):
        id = "-" + fe.id.name
        value = message(fe.value)
        ispan = fe.id.span or fe.span
        vspan = fe.value.span or fe.span
        comments = groupcomments + (
            fe.comment.content.split("\n") if fe.comment and fe.comment.content else []
        )
        yield Message((id,), value, (ispan.start, vspan.end), comments)
        for attr in fe.attributes:
            value = message(attr.value)
            span = attr.span or fe.span
            yield Message((id, attr.id.name), value, (span.start, span.end))
    elif isinstance(fe, Fluent.GroupComment):
        if fe.content:
            groupcomments[:] = fe.content.split("\n")
        else:
            groupcomments.clear()
    elif isinstance(fe, Fluent.Junk):
        raise ParseError(
            f"Fluent parse error at position {fe.span.start}:\n{fe.content}"
        )


def from_fluent(ast: Fluent.Resource) -> List[Message]:
    """
    Compile a Fluent resource into a message resource.
    """
    groupcomments = []
    return [entry for fe in ast.body for entry in messages(fe, groupcomments)]
