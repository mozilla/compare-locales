from __future__ import annotations

from collections import OrderedDict
from typing import Iterator, List, Optional, Tuple, Union

from fluent.syntax import ast as Fluent

from .elements import (
    CatchallKey,
    Comment,
    Entry,
    Expression,
    FunctionRef,
    Junk,
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


class SelectArg:
    def __init__(self, sel: Fluent.SelectExpression) -> None:
        self.defaultName = ""
        self.selector = sel.selector

        def getName(v: Fluent.Variant) -> Union[str, None]:
            name = v.key.name if isinstance(v.key, Fluent.Identifier) else v.key.value
            if v.default:
                self.defaultName = str(name)
                return None
            else:
                return name

        self.keys: List[Union[str, int, None]] = list(map(getName, sel.variants))


def findSelectArgs(pattern: Fluent.Pattern) -> List[SelectArg]:
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
                for arg in findSelectArgs(v.value):
                    add(arg)
    return args


def getOptions(args: Optional[Fluent.CallArguments]) -> OrderedDict[str, OptionValue]:
    options: OrderedDict[str, OptionValue] = OrderedDict()
    if args:
        for arg in args.named:
            options[arg.name.name] = (
                Literal(False, arg.value.value)
                if isinstance(arg.value, Fluent.NumberLiteral)
                else Literal(True, arg.value.parse()["value"])
            )
    return options


def expressionToPart(exp: Union[Fluent.Expression, Fluent.Placeable]) -> Expression:
    if isinstance(exp, Fluent.NumberLiteral):
        return FunctionRef("NUMBER", Literal(False, exp.value))
    elif isinstance(exp, Fluent.StringLiteral):
        return Literal(True, exp.parse()["value"])
    elif isinstance(exp, Fluent.VariableReference):
        return VariableRef(exp.id.name)
    elif isinstance(exp, Fluent.FunctionReference):
        args = [expressionToPart(exp) for exp in exp.arguments.positional]
        if len(args) > 1:
            raise Exception("More than one positional argument is not supported.")
        operand = args[0]
        if isinstance(operand, FunctionRef):
            raise Exception("A Fluent function is not supported here.")
        options = getOptions(exp.arguments)
        return FunctionRef(exp.id.name, operand, options)
    elif isinstance(exp, Fluent.MessageReference):
        msgId = (
            f"${exp.id.name}.${exp.attribute.name}" if exp.attribute else exp.id.name
        )
        return FunctionRef("MESSAGE", Literal(False, msgId))
    elif isinstance(exp, Fluent.TermReference):
        msgId = (
            "-${exp.id.name}.${exp.attribute.name}"
            if exp.attribute
            else f"-${exp.id.name}"
        )
        operand = Literal(False, msgId)
        options = getOptions(exp.arguments)
        return FunctionRef("MESSAGE", operand, options)
    elif isinstance(exp, Fluent.Placeable):
        return expressionToPart(exp.expression)
    raise Exception(f"${exp.__class__.__name__} not supported here")


def elementToPart(el: Union[Fluent.TextElement, Fluent.Placeable]) -> Expression | Text:
    if isinstance(el, Fluent.TextElement):
        return Text(el.value)
    else:
        return expressionToPart(el.expression)


def asFluentSelect(
    el: Union[Fluent.TextElement, Fluent.Placeable]
) -> Optional[Fluent.SelectExpression]:
    if isinstance(el, Fluent.TextElement):
        return None
    elif isinstance(el.expression, Fluent.SelectExpression):
        return el.expression
    elif isinstance(el.expression, Fluent.Placeable):
        return asFluentSelect(el.expression)
    else:
        return None


def messageFromFluentPattern(
    ast: Fluent.Pattern,
) -> Union[PatternMessage, SelectMessage]:
    """
    Compile a Fluent.Pattern (i.e. the value of a Fluent message or an attribute)
    into a Message data object.
    """
    args = findSelectArgs(ast)
    if len(args) == 0:
        return PatternMessage([elementToPart(el) for el in ast.elements])

    # First determine the keys for all cases, with empty values
    keys: List[List[Union[str, int, None]]]
    for i, arg in enumerate(args):
        kk: List[Union[str, int, None]] = []
        for key in arg.keys:
            if key not in kk:
                kk.append(key)
        kk.sort(key=lambda key: 1 if key is None else -1 if isinstance(key, int) else 0)
        if i == 0:
            keys = [[key] for key in kk]
        else:
            for i in range(len(keys), 0, -1):
                prev = keys[i - 1]
                keys[i - 1 : i] = [prev + [key] for key in kk]

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
            sel = asFluentSelect(el)
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
                        last = vp[-1]
                        part = elementToPart(el)
                        if isinstance(last, Text) and isinstance(part, Text):
                            last.value += part.value
                        else:
                            vp.append(part)

    addParts(ast, [])

    return SelectMessage([expressionToPart(arg.selector) for arg in args], variants)


def entriesFromFluent(fe: Fluent.EntryType) -> Iterator[Entry]:
    if not fe.span:
        raise Exception("Fluent parser must include spans in output")
    if isinstance(fe, Fluent.Message):
        id = fe.id.name
        cspan = fe.comment.span if fe.comment else None
        comment = (cspan.start, cspan.end) if cspan else None
        if fe.value:
            value = messageFromFluentPattern(fe.value)
            ispan = fe.id.span or fe.span
            vspan = fe.value.span or fe.span
            yield Message((id,), value, (ispan.start, vspan.end), comment)
            if comment:
                comment = None
        for attr in fe.attributes:
            value = messageFromFluentPattern(attr.value)
            span = attr.span or fe.span
            yield Message((id, attr.id.name), value, (span.start, span.end), comment)
            if comment:
                comment = None
    elif isinstance(fe, Fluent.Term):
        id = "-" + fe.id.name
        value = messageFromFluentPattern(fe.value)
        ispan = fe.id.span or fe.span
        vspan = fe.value.span or fe.span
        cspan = fe.comment.span if fe.comment else None
        comment = (cspan.start, cspan.end) if cspan else None
        yield Message((id,), value, (ispan.start, vspan.end), comment)
        for attr in fe.attributes:
            value = messageFromFluentPattern(attr.value)
            span = attr.span or span
            yield Message((id, attr.id.name), value, (span.start, span.end))
    else:
        span_ = (fe.span.start, fe.span.end)
        yield Comment(span_) if isinstance(fe, Fluent.BaseComment) else Junk(span_)


def resourceFromFluent(ast: Fluent.Resource) -> List[Entry]:
    """
    Compile a Fluent resource into a message resource.
    """
    return [entry for fe in ast.body for entry in entriesFromFluent(fe)]
