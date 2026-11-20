"""Build the single unified StratixConnector.cs NT8 AddOn (License Hub + PropPass + RocketPass)."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).parent


def extract_class_block(code: str, class_name: str) -> str:
    marker = f" public class {class_name} : AddOnBase {{"
    start = code.index(marker)
    # Strip trailing closing braces of namespace
    end = code.rfind("}")
    end = code.rfind("}", 0, end)
    return code[start:end + 1]


def main():
    prop_src = (ROOT / "StratixCandleService.cs").read_text(encoding="utf-8")
    rock_src = (ROOT / "RocketPassService.cs").read_text(encoding="utf-8")
    lic_frag = (ROOT / "StratixLicense.fragment.cs").read_text(encoding="utf-8")

    imports = "\n".join([
        "using System;",
        "using System.Collections.Generic;",
        "using System.IO;",
        "using System.Linq;",
        "using System.Text;",
        "using System.Windows;",
        "using System.Windows.Controls;",
        "using System.Windows.Media;",
        "using NinjaTrader.Cbi;",
        "using NinjaTrader.Data;",
        "using NinjaTrader.Gui;",
        "using NinjaTrader.Gui.Tools;",
        "using NinjaTrader.NinjaScript;",
    ])

    prop_class = extract_class_block(prop_src, "StratixCandleService")
    rock_class = extract_class_block(rock_src, "RocketPassService")

    unified = (
        "// STRATIX CONNECTOR UNIFICADO (Licencia + PropPass + RocketPass)\n"
        "// Archivo único para instalar en NinjaTrader 8\\bin\\Custom\\AddOns\\\n"
        + imports
        + "\nnamespace NinjaTrader.NinjaScript.AddOns {\n"
        + lic_frag
        + "\n"
        + prop_class
        + "\n"
        + rock_class
        + "\n}\n"
    )

    out_path = ROOT / "StratixConnector.cs"
    out_path.write_text(unified, encoding="utf-8")
    manifest = {
        "unified_addon": str(out_path),
        "modules": ["StratixSuiteMenu", "StratixCandleService", "RocketPassService"],
        "sha256": hashlib.sha256(unified.encode("utf-8")).hexdigest(),
        "compile_status": "PENDING",
    }
    (ROOT / "unified_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print("StratixConnector.cs unificado generado con éxito.")


if __name__ == "__main__":
    main()
