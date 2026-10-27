import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def literal(value):
    s = format(value, ".9g")
    if "." not in s and "e" not in s.lower(): s += ".0"
    return s + "f"


def main():
    model = json.loads((ROOT / "model.json").read_text())
    lines = ["#pragma once", "#include <stdint.h>", "// Generated small forest; no TFLite runtime or dynamic allocation.",
             "static constexpr float MILO_TRIGGER_THRESHOLD=" + literal(model["threshold"]) + ";",
             f"static constexpr int MILO_MODEL_FEATURES={len(model['feature_names'])};",
             "struct MiloNode { int16_t left,right; int8_t feature; float threshold,score; };"]
    for i, nodes in enumerate(model["trees"]):
        lines.append(f"static const MiloNode MILO_TREE_{i}[] = {{")
        for n in nodes:
            lines.append("{%d,%d,%d,%s,%s}," % (n["left"], n["right"], n["feature"], literal(n["threshold"]), literal(n["score"])))
        lines.append("};")
    lines += ["static inline float miloPredict(const float *x) {", "float score=0.0f;"]
    for i in range(len(model["trees"])):
        lines.append("{ int n=0; while(MILO_TREE_%d[n].feature>=0){ const MiloNode &v=MILO_TREE_%d[n];n=x[v.feature]<=v.threshold?v.left:v.right;}score+=MILO_TREE_%d[n].score;}" % (i, i, i))
    lines += [f"return score/{len(model['trees'])}.0f;", "}"]
    (ROOT / "GloveCandidateDetector/CandidateModel.h").write_text("\n".join(lines) + "\n")


if __name__ == "__main__": main()
