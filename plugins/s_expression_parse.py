import re
from os.path import exists, expanduser


term_regex = r"""(?mx)
    \s*(?:
        (?P<brackl>\()|
        (?P<brackr>\))|
        (?P<num>\-?\d+\.\d+|\-?\d+)|
        (?P<sq>"[^"]*")|
        (?P<s>[^(^)\s]+)
       )"""


# taken from https://rosettacode.org/wiki/S-Expressions#Python
def parse_sexp(sexp, dbg=False):
    stack = []
    out = []
    if dbg:
        print("%-6s %-14s %-44s %-s" % tuple("term value out stack".split()))
    for termtypes in re.finditer(term_regex, sexp):
        term, value = [(t, v) for t, v in termtypes.groupdict().items() if v][0]
        if dbg:
            print("%-7s %-14s %-44r %-r" % (term, value, out, stack))
        if term == "brackl":
            stack.append(out)
            out = []
        elif term == "brackr":
            assert stack, "Trouble with nesting of brackets"
            tmpout, out = out, stack.pop(-1)
            out.append(tmpout)
        elif term == "num":
            v = float(value)
            if v.is_integer():
                v = int(v)
            out.append(v)
        elif term == "sq":
            out.append(value[1:-1])
        elif term == "s":
            out.append(value)
        else:
            raise NotImplementedError("Error: %r" % (term, value))
    assert not stack, "Trouble with nesting of brackets"
    return out[0]


def print_sexp(exp):
    out = ""
    if type(exp) == type([]):
        out += "(" + " ".join(print_sexp(x) for x in exp) + ")"
    elif type(exp) == type("") and re.search(r"[\s()]", exp):
        out += '"%s"' % repr(exp)[1:-1].replace('"', '"')
    else:
        out += "%s" % exp
    return out


def readFile2var(path):
    path = expanduser(path)

    if not exists(path):
        return None

    with open(path, "r") as file:
        data = file.read()
    return data


def convert_list_to_dicts(data):
    dict_list = []
    for entry in data:
        if not type(entry) == list:
            continue
        entry_dict = {}
        for item in entry:
            if type(item) == list and len(item) == 2:
                key, value = item
                entry_dict[key] = value
        if len(entry_dict):
            dict_list.append(entry_dict)
    return dict_list


if __name__ == "__main__":
    from pprint import pprint

    sexp = """(sym_lib_table
    (version 7)
    (lib (name "4xxx")(type "KiCad")(uri "${KICAD7_SYMBOL_DIR}/4xxx.kicad_sym")(options "")(descr "4xxx series symbols"))
    (lib (name "4xxx_IEEE")(type "KiCad")(uri "${KICAD7_SYMBOL_DIR}/4xxx_IEEE.kicad_sym")(options "")(descr "4xxx series IEEE symbols"))
    (lib (name "74xGxx")(type "KiCad")(uri "${KICAD7_SYMBOL_DIR}/74xGxx.kicad_sym")(options "")(descr "74xGxx symbols"))
    (lib (name "74xx")(type "KiCad")(uri "${KICAD7_SYMBOL_DIR}/74xx.kicad_sym")(options "")(descr "74xx symbols"))
    (lib (name "74xx_IEEE")(type "KiCad")(uri "${KICAD7_SYMBOL_DIR}/74xx_IEEE.kicad_sym")(options "")(descr "74xx series IEEE symbols"))
    )"""

    dir_ = "~/.config/kicad/8.0/sym-lib-table"
    dir_ = "~/.config/kicad/8.0/fp-lib-table"
    sexp = readFile2var(dir_)

    parsed = parse_sexp(sexp)
    # pprint(parsed)
    parsed_dict = convert_list_to_dicts(parsed[0:10])
    pprint(parsed_dict)
