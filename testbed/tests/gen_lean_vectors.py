"""Write the test vectors of vectors.json into lean/TopoPQC.lean as theorems.

  python3 tests/gen_lean_vectors.py     # rewrites the generated block in place
The block sits between the BEGIN/END markers; test_properties.py checks it is current.
"""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
LEAN = os.path.join(HERE, "..", "..", "lean", "TopoPQC.lean")
BEGIN, END = "-- BEGIN GENERATED TEST VECTORS", "-- END GENERATED TEST VECTORS"


def lean_num(x):
    return f"({x})" if x < 0 else str(x)


def block():
    vs = json.load(open(os.path.join(HERE, "vectors.json")))["vectors"]
    out = [BEGIN,
           "/-! Test vectors shared with `testbed/tests/vectors.json`; each value is also checked",
           "against the scorer `tools/score.py` by `testbed/tests/test_properties.py`. -/", ""]
    for v in vs:
        args = " ".join(lean_num(v[k]) for k in ("tfix", "H", "L", "T"))
        out += [f"/-- {v['note']} -/",
                f"theorem vec_{v['name']} : W {args} = {lean_num(v['W'])} := by",
                "  norm_num [W, max_def]", ""]
    out.append(END)
    return "\n".join(out)


def splice(text, new):
    if BEGIN in text:
        i, j = text.index(BEGIN), text.index(END) + len(END)
        return text[:i] + new + text[j:]
    k = text.rindex("end TopoPQC")
    return text[:k] + new + "\n\n" + text[k:]


if __name__ == "__main__":
    t = open(LEAN).read()
    open(LEAN, "w").write(splice(t, block()))
    print("wrote", LEAN)
