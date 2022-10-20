"""
NetworkX is distributed with the 3-clause BSD license.

::

   Copyright (C) 2004-2022, NetworkX Developers
   Aric Hagberg <hagberg@lanl.gov>
   Dan Schult <dschult@colgate.edu>
   Pieter Swart <swart@lanl.gov>
   All rights reserved.

   Redistribution and use in source and binary forms, with or without
   modification, are permitted provided that the following conditions are
   met:

     * Redistributions of source code must retain the above copyright
       notice, this list of conditions and the following disclaimer.

     * Redistributions in binary form must reproduce the above
       copyright notice, this list of conditions and the following
       disclaimer in the documentation and/or other materials provided
       with the distribution.

     * Neither the name of the NetworkX Developers nor the names of its
       contributors may be used to endorse or promote products derived
       from this software without specific prior written permission.

   THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS
   "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT
   LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR
   A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT
   OWNER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL,
   SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT
   LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE,
   DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY
   THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
   (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
   OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
"""

"""
Read graphs in GML format.

"GML, the Graph Modelling Language, is our proposal for a portable
file format for graphs. GML's key features are portability, simple
syntax, extensibility and flexibility. A GML file consists of a
hierarchical key-value lists. Graphs can be annotated with arbitrary
data structures. The idea for a common file format was born at the
GD'95; this proposal is the outcome of many discussions. GML is the
standard file format in the Graphlet graph editor system. It has been
overtaken and adapted by several other systems for drawing graphs."

GML files are stored using a 7-bit ASCII encoding with any extended
ASCII characters (iso8859-1) appearing as HTML character entities.
You will need to give some thought into how the exported data should
interact with different languages and even different Python versions.
Re-importing from gml is also a concern.

Without specifying a `stringizer`/`destringizer`, the code is capable of
writing `int`/`float`/`str`/`dict`/`list` data as required by the GML
specification.  For writing other data types, and for reading data other
than `str` you need to explicitly supply a `stringizer`/`destringizer`.

For additional documentation on the GML file format, please see the
`GML website <https://web.archive.org/web/20190207140002/http://www.fim.uni-passau.de/index.php?id=17297&L=1>`_.

Several example graphs in GML format may be found on Mark Newman's
`Network data page <http://www-personal.umich.edu/~mejn/netdata/>`_.
"""
from io import StringIO
from ast import literal_eval
from collections import defaultdict
from enum import Enum
from typing import Any, NamedTuple

import warnings
import re
import html.entities as htmlentitydefs

__all__ = ["read_gml", "parse_gml", "generate_gml", "write_gml"]


def escape(text):
    """Use XML character references to escape characters.

    Use XML character references for unprintable or non-ASCII
    characters, double quotes and ampersands in a string
    """

    def fixup(m):
        ch = m.group(0)
        return "&#" + str(ord(ch)) + ";"

    text = re.sub('[^ -~]|[&"]', fixup, text)
    return text if isinstance(text, str) else str(text)


def unescape(text):
    """Replace XML character references with the referenced characters"""

    def fixup(m):
        text = m.group(0)
        if text[1] == "#":
            # Character reference
            if text[2] == "x":
                code = int(text[3:-1], 16)
            else:
                code = int(text[2:-1])
        else:
            # Named entity
            try:
                code = htmlentitydefs.name2codepoint[text[1:-1]]
            except KeyError:
                return text  # leave unchanged
        try:
            return chr(code)
        except (ValueError, OverflowError):
            return text  # leave unchanged

    return re.sub("&(?:[0-9A-Za-z]+|#(?:[0-9]+|x[0-9A-Fa-f]+));", fixup, text)


def literal_destringizer(rep):
    """Convert a Python literal to the value it represents.

    Parameters
    ----------
    rep : string
        A Python literal.

    Returns
    -------
    value : object
        The value of the Python literal.

    Raises
    ------
    ValueError
        If `rep` is not a Python literal.
    """
    msg = "literal_destringizer is deprecated and will be removed in 3.0."
    warnings.warn(msg, DeprecationWarning)
    if isinstance(rep, str):
        orig_rep = rep
        try:
            return literal_eval(rep)
        except SyntaxError as e:
            raise ValueError(f"{orig_rep!r} is not a valid Python literal") from e
    else:
        raise ValueError(f"{rep!r} is not a string")

def read_gml(file, label="label", destringizer=None):
    """Read graph in GML format from `path`.

    Parameters
    ----------
    file : filehandle
        The filehandle to read from.

    label : string, optional
        If not None, the parsed nodes will be renamed according to node
        attributes indicated by `label`. Default value: 'label'.

    destringizer : callable, optional
        A `destringizer` that recovers values stored as strings in GML. If it
        cannot convert a string to a value, a `ValueError` is raised. Default
        value : None.

    Returns
    -------
    G : NetworkX graph
        The parsed graph.

    Raises
    ------
    ValueError
        If the input cannot be parsed.

    See Also
    --------
    write_gml, parse_gml

    Notes
    -----
    GML files are stored using a 7-bit ASCII encoding with any extended
    ASCII characters (iso8859-1) appearing as HTML character entities.
    Without specifying a `stringizer`/`destringizer`, the code is capable of
    writing `int`/`float`/`str`/`dict`/`list` data as required by the GML
    specification.  For writing other data types, and for reading data other
    than `str` you need to explicitly supply a `stringizer`/`destringizer`.

    For additional documentation on the GML file format, please see the
    `GML url <https://web.archive.org/web/20190207140002/http://www.fim.uni-passau.de/index.php?id=17297&L=1>`_.

    See the module docstring :mod:`networkx.readwrite.gml` for more details.

    Examples
    --------
    >>> G = nx.path_graph(4)
    >>> nx.write_gml(G, "test.gml")

    GML values are interpreted as strings by default:

    >>> H = nx.read_gml("test.gml")
    >>> H.nodes
    NodeView(('0', '1', '2', '3'))

    When a `destringizer` is provided, GML values are converted to the provided type.
    For example, integer nodes can be recovered as shown below:

    >>> J = nx.read_gml("test.gml", destringizer=int)
    >>> J.nodes
    NodeView((0, 1, 2, 3))

    """

    def filter_lines(lines):
        for line in lines:
            try:
                line = line.decode("ascii")
            except UnicodeDecodeError as e:
                raise ValueError("input is not ASCII-encoded") from e
            if not isinstance(line, str):
                lines = str(lines)
            if line and line[-1] == "\n":
                line = line[:-1]
            yield line

    G = parse_gml_lines(filter_lines(file), label, destringizer)
    return G


def parse_gml(lines, label="label", destringizer=None):
    """Parse GML graph from a string or iterable.

    Parameters
    ----------
    lines : string or iterable of strings
       Data in GML format.

    label : string, optional
        If not None, the parsed nodes will be renamed according to node
        attributes indicated by `label`. Default value: 'label'.

    destringizer : callable, optional
        A `destringizer` that recovers values stored as strings in GML. If it
        cannot convert a string to a value, a `ValueError` is raised. Default
        value : None.

    Returns
    -------
    G : NetworkX graph
        The parsed graph.

    Raises
    ------
    ValueError
        If the input cannot be parsed.

    See Also
    --------
    write_gml, read_gml

    Notes
    -----
    This stores nested GML attributes as dictionaries in the NetworkX graph,
    node, and edge attribute structures.

    GML files are stored using a 7-bit ASCII encoding with any extended
    ASCII characters (iso8859-1) appearing as HTML character entities.
    Without specifying a `stringizer`/`destringizer`, the code is capable of
    writing `int`/`float`/`str`/`dict`/`list` data as required by the GML
    specification.  For writing other data types, and for reading data other
    than `str` you need to explicitly supply a `stringizer`/`destringizer`.

    For additional documentation on the GML file format, please see the
    `GML url <https://web.archive.org/web/20190207140002/http://www.fim.uni-passau.de/index.php?id=17297&L=1>`_.

    See the module docstring :mod:`networkx.readwrite.gml` for more details.
    """

    def decode_line(line):
        if isinstance(line, bytes):
            try:
                line.decode("ascii")
            except UnicodeDecodeError as e:
                raise ValueError("input is not ASCII-encoded") from e
        if not isinstance(line, str):
            line = str(line)
        return line

    def filter_lines(lines):
        if isinstance(lines, str):
            lines = decode_line(lines)
            lines = lines.splitlines()
            yield from lines
        else:
            for line in lines:
                line = decode_line(line)
                if line and line[-1] == "\n":
                    line = line[:-1]
                if line.find("\n") != -1:
                    raise ValueError("input line contains newline")
                yield line

    G = parse_gml_lines(filter_lines(lines), label, destringizer)
    return G


class Pattern(Enum):
    """encodes the index of each token-matching pattern in `tokenize`."""

    KEYS = 0
    REALS = 1
    INTS = 2
    STRINGS = 3
    DICT_START = 4
    DICT_END = 5
    COMMENT_WHITESPACE = 6


class Token(NamedTuple):
    category: Pattern
    value: Any
    line: int
    position: int


LIST_START_VALUE = "_networkx_list_start"


def parse_gml_lines(lines, label, destringizer):
    """Parse GML `lines` into a graph."""

    def tokenize():
        patterns = [
            r"[A-Za-z][0-9A-Za-z_]*\b",  # keys
            # reals
            r"[+-]?(?:[0-9]*\.[0-9]+|[0-9]+\.[0-9]*|INF)(?:[Ee][+-]?[0-9]+)?",
            r"[+-]?[0-9]+",  # ints
            r'".*?"',  # strings
            r"\[",  # dict start
            r"\]",  # dict end
            r"#.*$|\s+",  # comments and whitespaces
        ]
        tokens = re.compile("|".join(f"({pattern})" for pattern in patterns))
        lineno = 0
        for line in lines:
            length = len(line)
            pos = 0
            while pos < length:
                match = tokens.match(line, pos)
                if match is None:
                    m = f"cannot tokenize {line[pos:]} at ({lineno + 1}, {pos + 1})"
                    raise ValueError(m)
                for i in range(len(patterns)):
                    group = match.group(i + 1)
                    if group is not None:
                        if i == 0:  # keys
                            value = group.rstrip()
                        elif i == 1:  # reals
                            value = float(group)
                        elif i == 2:  # ints
                            value = int(group)
                        else:
                            value = group
                        if i != 6:  # comments and whitespaces
                            yield Token(Pattern(i), value, lineno + 1, pos + 1)
                        pos += len(group)
                        break
            lineno += 1
        yield Token(None, None, lineno + 1, 1)  # EOF

    def unexpected(curr_token, expected):
        category, value, lineno, pos = curr_token
        value = repr(value) if value is not None else "EOF"
        raise ValueError(f"expected {expected}, found {value} at ({lineno}, {pos})")

    def consume(curr_token, category, expected):
        if curr_token.category == category:
            return next(tokens)
        unexpected(curr_token, expected)

    def parse_kv(curr_token):
        dct = defaultdict(list)
        while curr_token.category == Pattern.KEYS:
            key = curr_token.value
            curr_token = next(tokens)
            category = curr_token.category
            if category == Pattern.REALS or category == Pattern.INTS:
                value = curr_token.value
                curr_token = next(tokens)
            elif category == Pattern.STRINGS:
                value = unescape(curr_token.value[1:-1])
                if destringizer:
                    try:
                        value = destringizer(value)
                    except ValueError:
                        pass
                curr_token = next(tokens)
            elif category == Pattern.DICT_START:
                curr_token, value = parse_dict(curr_token)
            else:
                # Allow for string convertible id and label values
                if key in ("id", "label", "source", "target"):
                    try:
                        # String convert the token value
                        value = unescape(str(curr_token.value))
                        if destringizer:
                            try:
                                value = destringizer(value)
                            except ValueError:
                                pass
                        curr_token = next(tokens)
                    except Exception:
                        msg = (
                                "an int, float, string, '[' or string"
                                + " convertable ASCII value for node id or label"
                        )
                        unexpected(curr_token, msg)
                # Special handling for nan and infinity.  Since the gml language
                # defines unquoted strings as keys, the numeric and string branches
                # are skipped and we end up in this special branch, so we need to
                # convert the current token value to a float for NAN and plain INF.
                # +/-INF are handled in the pattern for 'reals' in tokenize().  This
                # allows labels and values to be nan or infinity, but not keys.
                elif curr_token.value in {"NAN", "INF"}:
                    value = float(curr_token.value)
                    curr_token = next(tokens)
                else:  # Otherwise error out
                    unexpected(curr_token, "an int, float, string or '['")
            dct[key].append(value)

        def clean_dict_value(value):
            if not isinstance(value, list):
                return value
            if len(value) == 1:
                return value[0]
            if value[0] == LIST_START_VALUE:
                return value[1:]
            return value

        dct = {key: clean_dict_value(value) for key, value in dct.items()}
        return curr_token, dct

    def parse_dict(curr_token):
        # dict start
        curr_token = consume(curr_token, Pattern.DICT_START, "'['")
        # dict contents
        curr_token, dct = parse_kv(curr_token)
        # dict end
        curr_token = consume(curr_token, Pattern.DICT_END, "']'")
        return curr_token, dct

    def parse_graph():
        curr_token, dct = parse_kv(next(tokens))
        if curr_token.category is not None:  # EOF
            unexpected(curr_token, "EOF")
        if "graph" not in dct:
            raise ValueError("input contains no graph")
        graph = dct["graph"]
        if isinstance(graph, list):
            raise ValueError("input contains more than one graph")
        return graph

    tokens = tokenize()
    graph = parse_graph()
    return graph


def literal_stringizer(value):
    """Convert a `value` to a Python literal in GML representation.

    Parameters
    ----------
    value : object
        The `value` to be converted to GML representation.

    Returns
    -------
    rep : string
        A double-quoted Python literal representing value. Unprintable
        characters are replaced by XML character references.

    Raises
    ------
    ValueError
        If `value` cannot be converted to GML.

    Notes
    -----
    `literal_stringizer` is largely the same as `repr` in terms of
    functionality but attempts prefix `unicode` and `bytes` literals with
    `u` and `b` to provide better interoperability of data generated by
    Python 2 and Python 3.

    The original value can be recovered using the
    :func:`networkx.readwrite.gml.literal_destringizer` function.
    """
    msg = "literal_stringizer is deprecated and will be removed in 3.0."
    warnings.warn(msg, DeprecationWarning)

    def stringize(value):
        if isinstance(value, (int, bool)) or value is None:
            if value is True:  # GML uses 1/0 for boolean values.
                buf.write(str(1))
            elif value is False:
                buf.write(str(0))
            else:
                buf.write(str(value))
        elif isinstance(value, str):
            text = repr(value)
            if text[0] != "u":
                try:
                    value.encode("latin1")
                except UnicodeEncodeError:
                    text = "u" + text
            buf.write(text)
        elif isinstance(value, (float, complex, str, bytes)):
            buf.write(repr(value))
        elif isinstance(value, list):
            buf.write("[")
            first = True
            for item in value:
                if not first:
                    buf.write(",")
                else:
                    first = False
                stringize(item)
            buf.write("]")
        elif isinstance(value, tuple):
            if len(value) > 1:
                buf.write("(")
                first = True
                for item in value:
                    if not first:
                        buf.write(",")
                    else:
                        first = False
                    stringize(item)
                buf.write(")")
            elif value:
                buf.write("(")
                stringize(value[0])
                buf.write(",)")
            else:
                buf.write("()")
        elif isinstance(value, dict):
            buf.write("{")
            first = True
            for key, value in value.items():
                if not first:
                    buf.write(",")
                else:
                    first = False
                stringize(key)
                buf.write(":")
                stringize(value)
            buf.write("}")
        elif isinstance(value, set):
            buf.write("{")
            first = True
            for item in value:
                if not first:
                    buf.write(",")
                else:
                    first = False
                stringize(item)
            buf.write("}")
        else:
            msg = "{value!r} cannot be converted into a Python literal"
            raise ValueError(msg)

    buf = StringIO()
    stringize(value)
    return buf.getvalue()


def generate_gml(G, stringizer=None):
    r"""Generate a single entry of the graph `G` in GML format.

    Parameters
    ----------
    G : dictionary
        The graph to be converted to GML.

    stringizer : callable, optional
        A `stringizer` which converts non-int/non-float/non-dict values into
        strings. If it cannot convert a value into a string, it should raise a
        `ValueError` to indicate that. Default value: None.

    Returns
    -------
    lines: generator of strings
        Lines of GML data. Newlines are not appended.

    Raises
    ------
    ValueError
        If `stringizer` cannot convert a value into a string, or the value to
        convert is not a string while `stringizer` is None.

    Notes
    -----
    Graph attributes named 'directed', 'multigraph', 'node' or
    'edge', node attributes named 'id' or 'label', edge attributes
    named 'source' or 'target' (or 'key' if `G` is a multigraph)
    are ignored because these attribute names are used to encode the graph
    structure.

    GML files are stored using a 7-bit ASCII encoding with any extended
    ASCII characters (iso8859-1) appearing as HTML character entities.
    Without specifying a `stringizer`/`destringizer`, the code is capable of
    writing `int`/`float`/`str`/`dict`/`list` data as required by the GML
    specification.  For writing other data types, and for reading data other
    than `str` you need to explicitly supply a `stringizer`/`destringizer`.

    For additional documentation on the GML file format, please see the
    `GML url <https://web.archive.org/web/20190207140002/http://www.fim.uni-passau.de/index.php?id=17297&L=1>`_.

    See the module docstring :mod:`networkx.readwrite.gml` for more details.

    Examples
    --------
    >>> G = nx.Graph()
    >>> G.add_node("1")
    >>> print("\n".join(nx.generate_gml(G)))
    graph [
      node [
        id 0
        label "1"
      ]
    ]
    >>> G = nx.OrderedMultiGraph([("a", "b"), ("a", "b")])
    >>> print("\n".join(nx.generate_gml(G)))
    graph [
      multigraph 1
      node [
        id 0
        label "a"
      ]
      node [
        id 1
        label "b"
      ]
      edge [
        source 0
        target 1
        key 0
      ]
      edge [
        source 0
        target 1
        key 1
      ]
    ]
    """
    valid_keys = re.compile("^[A-Za-z][0-9A-Za-z_]*$")

    def stringize(key, value, ignored_keys, indent, in_list=False):
        if not isinstance(key, str):
            raise ValueError(f"{key!r} is not a string")
        if not valid_keys.match(key):
            raise ValueError(f"{key!r} is not a valid key")
        if not isinstance(key, str):
            key = str(key)
        if key not in ignored_keys:
            if isinstance(value, (int, bool)):
                if key == "label":
                    yield indent + key + ' "' + str(value) + '"'
                elif value is True:
                    # python bool is an instance of int
                    yield indent + key + " 1"
                elif value is False:
                    yield indent + key + " 0"
                # GML only supports signed 32-bit integers
                elif value < -(2 ** 31) or value >= 2 ** 31:
                    yield indent + key + ' "' + str(value) + '"'
                else:
                    yield indent + key + " " + str(value)
            elif isinstance(value, float):
                text = repr(value).upper()
                # GML matches INF to keys, so prepend + to INF. Use repr(float(*))
                # instead of string literal to future proof against changes to repr.
                if text == repr(float("inf")).upper():
                    text = "+" + text
                else:
                    # GML requires that a real literal contain a decimal point, but
                    # repr may not output a decimal point when the mantissa is
                    # integral and hence needs fixing.
                    epos = text.rfind("E")
                    if epos != -1 and text.find(".", 0, epos) == -1:
                        text = text[:epos] + "." + text[epos:]
                if key == "label":
                    yield indent + key + ' "' + text + '"'
                else:
                    yield indent + key + " " + text
            elif isinstance(value, dict):
                yield indent + key + " ["
                next_indent = indent + "  "
                for key, value in value.items():
                    yield from stringize(key, value, (), next_indent)
                yield indent + "]"
            elif (
                    isinstance(value, (list, tuple))
                    and key != "label"
                    and value
                    and not in_list
            ):
                if len(value) == 1:
                    yield indent + key + " " + f'"{LIST_START_VALUE}"'
                for val in value:
                    yield from stringize(key, val, (), indent, True)
            else:
                if stringizer:
                    try:
                        value = stringizer(value)
                    except ValueError as e:
                        raise ValueError(
                            f"{value!r} cannot be converted into a string"
                        ) from e
                if not isinstance(value, str):
                    raise ValueError(f"{value!r} is not a string")
                yield indent + key + ' "' + escape(value) + '"'

    for attr, value in G.items():
        yield from stringize(attr, value, {}, "")


def write_gml(G, file, stringizer=None):
    """Write a graph `G` in GML format to the file or file handle `path`.

    Parameters
    ----------
    G : graph dictionary
        The graph to be converted to GML.

    file : filehandle
        The filehandle to write. Files whose names end with .gz or
        .bz2 will be compressed.

    stringizer : callable, optional
        A `stringizer` which converts non-int/non-float/non-dict values into
        strings. If it cannot convert a value into a string, it should raise a
        `ValueError` to indicate that. Default value: None.

    Raises
    ------
    ValueError
        If `stringizer` cannot convert a value into a string, or the value to
        convert is not a string while `stringizer` is None.

    See Also
    --------
    read_gml, generate_gml

    Notes
    -----
    Graph attributes named 'directed', 'multigraph', 'node' or
    'edge', node attributes named 'id' or 'label', edge attributes
    named 'source' or 'target' (or 'key' if `G` is a multigraph)
    are ignored because these attribute names are used to encode the graph
    structure.

    GML files are stored using a 7-bit ASCII encoding with any extended
    ASCII characters (iso8859-1) appearing as HTML character entities.
    Without specifying a `stringizer`/`destringizer`, the code is capable of
    writing `int`/`float`/`str`/`dict`/`list` data as required by the GML
    specification.  For writing other data types, and for reading data other
    than `str` you need to explicitly supply a `stringizer`/`destringizer`.

    Note that while we allow non-standard GML to be read from a file, we make
    sure to write GML format. In particular, underscores are not allowed in
    attribute names.
    For additional documentation on the GML file format, please see the
    `GML url <https://web.archive.org/web/20190207140002/http://www.fim.uni-passau.de/index.php?id=17297&L=1>`_.

    See the module docstring :mod:`networkx.readwrite.gml` for more details.

    Examples
    --------
    >>> G = nx.path_graph(4)
    >>> nx.write_gml(G, "test.gml")

    Filenames ending in .gz or .bz2 will be compressed.

    >>> nx.write_gml(G, "test.gml.gz")
    """
    content = {
        "Creator": "taf-python-server",
        "Version": "20221016",
        "graph": G
    }
    for line in generate_gml(content, stringizer):
        file.write((line + "\n").encode("ascii"))
