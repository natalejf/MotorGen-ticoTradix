"""Generate a separate NT8 strategy without modifying the user's original."""
import hashlib
import json
from pathlib import Path

SOURCE=Path(r'C:\Users\yo\OneDrive\Escritorio\NinjaTrader EA Evals\CandleController.cs')
ROOT=Path(__file__).parent


def main():
    original=SOURCE.read_bytes();text=original.decode('utf-8-sig')
    def replace(old,new):
        nonlocal text
        if text.count(old)!=1:raise RuntimeError('El código original cambió: revisar integración '+old[:70])
        text=text.replace(old,new,1)
    replace('public class ChallengeCandleController : Strategy','public class StratixChallengeCandleController : Strategy')
    replace('Name = "ChallengeCandleController";',
            'Name = "StratixChallengeCandleController";\n                StratixWebEnabled = false; StratixConnectionId = ""; StratixConnectionKey = "";')
    replace('"ChallengeCandleConfig.txt"','"StratixChallengeCandleConfig.txt"')
    replace('Lots = 10;', 'Lots = 1; // Conservative default for the separate Sim101 integration.')
    replace('globalConfig.Lots = 40;', 'globalConfig.Lots = 1; // Sim101 integration default.')
    replace('private Account GetAccountCached(string name)\n        {',
            'private Account GetAccountCached(string name)\n        {\n            if (StratixWebEnabled && !string.Equals(name, "Sim101", StringComparison.Ordinal)) return null;')
    replace('private void SubmitOrderToAccount(Account acc, OrderAction action, OrderType type, int qty, double price, string name)\n        {',
            'private void SubmitOrderToAccount(Account acc, OrderAction action, OrderType type, int qty, double price, string name)\n        {\n            if (StratixWebEnabled && (acc == null || acc.Name != "Sim101")) throw new Exception("Stratix web solo Sim101");')
    replace('private void UiRefreshTimer_Tick(object sender, EventArgs e)\n        {',
            'private void UiRefreshTimer_Tick(object sender, EventArgs e)\n        {\n            StratixWebPulse();')
    replace('private bool masterTradingEnabled = false;',
            ROOT.joinpath('StratixControllerBridge.fragment.cs').read_text(encoding='utf-8')+'\n        private bool masterTradingEnabled = false;')
    replace('protected override void OnBarUpdate()\n        {',
            'protected override void OnBarUpdate()\n        {\n            if (StratixWebEnabled && (DateTime.UtcNow - stratixLastSuccess).TotalSeconds > 10) masterTradingEnabled = false;')
    ROOT.joinpath('StratixChallengeCandleController.cs').write_text(text,encoding='utf-8')
    ROOT.joinpath('source_manifest.json').write_text(json.dumps(dict(source=str(SOURCE),sha256=hashlib.sha256(original).hexdigest(),
        original_unchanged=True,platform='NinjaTrader 8',native_compile_status='PENDING_NINJATRADER_EDITOR'),indent=2),encoding='utf-8')
    print('Copia integrada generada; original sin cambios. Compilar en NinjaTrader 8 antes de usar.')


if __name__=='__main__':main()
