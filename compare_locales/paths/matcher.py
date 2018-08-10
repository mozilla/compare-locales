# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

from __future__ import absolute_import
import re
import itertools
from compare_locales import mozpath
import six


class Matcher(object):
    '''Path pattern matcher
    Supports path matching similar to mozpath.match(), but does
    not match trailing file paths without trailing wildcards.
    Also gets a prefix, which is the path before the first wildcard,
    which is good for filesystem iterations, and allows to replace
    the own matches in a path on a different Matcher. compare-locales
    uses that to transform l10n and en-US paths back and forth.
    '''

    def __init__(self, pattern_or_other, env={}, root=None):
        '''Create regular expression similar to mozpath.match().
        '''
        parser = PatternParser()
        real_env = {k: parser.parse(v) for k, v in env.items()}
        self._cached_re = None
        if root is not None:
            # make sure that our root is fully expanded and ends with /
            root = mozpath.abspath(root) + '/'
        # allow constructing Matchers from Matchers
        if isinstance(pattern_or_other, Matcher):
            other = pattern_or_other
            self.pattern = Pattern(other.pattern)
            self.env = other.env.copy()
            self.env.update(real_env)
            if root is not None:
                self.pattern.root = root
            return
        self.env = real_env
        pattern = pattern_or_other
        self.pattern = parser.parse(pattern)
        if root is not None:
            self.pattern.root = root

    def with_env(self, environ):
        return Matcher(self, environ)

    @property
    def prefix(self):
        subpattern = Pattern(self.pattern[:self.pattern.prefix_length])
        subpattern.root = self.pattern.root
        return subpattern.expand(self.env)

    def match(self, path):
        '''
        True if the given path matches the file pattern.
        '''
        self._cache_regex()
        return re.match(self._cached_re, path)

    def _cache_regex(self):
        if self._cached_re is not None:
            return
        self._cached_re = re.compile(
            self.pattern.regex_pattern(self.env) + '$'
        )

    def sub(self, other, path):
        '''
        Replace the wildcard matches in this pattern into the
        pattern of the other Match object.
        '''
        m = self.match(path)
        if m is None:
            return None
        env = {}
        env.update(
            (key, Literal(value))
            for key, value in m.groupdict().items()
        )
        env.update(other.env)
        return other.pattern.expand(env)


def expand(root, path, env):
    '''Expand a given path relative to the given root,
    using the given env to resolve variables.

    This will break if the path contains wildcards.
    '''
    pattern = Matcher(path, env=env, root=root).pattern
    return pattern.expand(env)


class Node(object):
    '''Abstract base class for all nodes in parsed patterns.'''
    def regex_pattern(self, env):
        '''Create a regular expression fragment for this Node.'''
        raise NotImplementedError

    def expand(self, env):
        '''Convert this node to a string with the given environment.'''
        raise NotImplementedError


class Pattern(list, Node):
    def __init__(self, iterable=[]):
        list.__init__(self, iterable)
        self.root = getattr(iterable, 'root', None)
        self.prefix_length = getattr(iterable, 'prefix_length', None)

    def regex_pattern(self, env):
        root = ''
        if self.root is not None:
            # make sure we're not hiding a full path
            first_seg = self[0].expand(env)
            if not first_seg.startswith('/'):
                root = re.escape(self.root)
        return root + ''.join(
            child.regex_pattern(env) for child in self
        )

    def expand(self, env):
        root = ''
        if self.root is not None:
            # make sure we're not hiding a full path
            first_seg = self[0].expand(env)
            if not first_seg.startswith('/'):
                root = self.root
        return root + ''.join(
            child.expand(env) for child in self
        )


class Literal(six.text_type, Node):
    def regex_pattern(self, env):
        return re.escape(self)

    def expand(self, env):
        return self


class Variable(Node):
    def __init__(self, name, repeat=False):
        self.name = name
        self.repeat = repeat

    def regex_pattern(self, env):
        if self.repeat:
            return '(?P={})'.format(self.name)
        if self.name in env:
            # make sure we match the value in the environment
            body = env[self.name].regex_pattern(self._no_cycle(env))
        else:
            # match anything, including path segments
            body = '.+?'
        return '(?P<{}>{})'.format(self.name, body)

    def expand(self, env):
        '''Create a string for this Variable.

        This expansion happens recursively. We avoid recusion loops
        by removing the current variable from the environment that's used
        to expand child variable references.
        '''
        return env.get(self.name, Literal('')).expand(self._no_cycle(env))

    def _no_cycle(self, env):
        '''Remove our variable name from the environment.
        That way, we can't create cyclic references.
        '''
        if self.name not in env:
            return env
        env = env.copy()
        env.pop(self.name)
        return env


class Star(Node):
    def __init__(self, number):
        self.number = number

    def regex_pattern(self, env):
        return '(?P<s{}>[^/]*)'.format(self.number)

    def expand(self, env):
        return env['s%d' % self.number]


class Starstar(Star):
    def __init__(self, number, suffix):
        self.number = number
        self.suffix = suffix

    def regex_pattern(self, env):
        return '(?P<s{}>.+{})?'.format(self.number, self.suffix)


PATH_SPECIAL = re.compile(
    r'(?P<starstar>(?<![^/])\*\*(?P<suffix>/|$))'
    r'|'
    r'(?P<star>\*)'
    r'|'
    r'(?P<variable>{ *(?P<varname>[\w]+) *})'
)


class PatternParser(object):
    def __init__(self):
        # Not really initializing anything, just making room for our
        # result and state members.
        self.pattern = None
        self._stargroup = self._cursor = None
        self._known_vars = None

    def parse(self, pattern):
        # Initializing result and state
        self.pattern = Pattern()
        self._stargroup = itertools.count(1)
        self._known_vars = set()
        self._cursor = 0
        for match in PATH_SPECIAL.finditer(pattern):
            if match.start() > self._cursor:
                self.pattern.append(
                    Literal(pattern[self._cursor:match.start()])
                )
            self.handle(match)
        self.pattern.append(Literal(pattern[self._cursor:]))
        if self.pattern.prefix_length is None:
            self.pattern.prefix_length = len(self.pattern)
        return self.pattern

    def handle(self, match):
        if match.group('variable'):
            self.variable(match)
        else:
            self.wildcard(match)
        self._cursor = match.end()

    def variable(self, match):
        varname = match.group('varname')
        self.pattern.append(Variable(varname, varname in self._known_vars))
        self._known_vars.add(varname)

    def wildcard(self, match):
        # wildcard found, stop prefix
        if self.pattern.prefix_length is None:
            self.pattern.prefix_length = len(self.pattern)
        wildcard = next(self._stargroup)
        if match.group('star'):
            # *
            self.pattern.append(Star(wildcard))
        else:
            # **
            self.pattern.append(Starstar(wildcard, match.group('suffix')))