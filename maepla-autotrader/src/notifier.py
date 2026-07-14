from src.config import get
from src.logger import get_logger

logger = get_logger()


class Notifier:
    def __init__(self):
        cfg = get()
        self.token = cfg.line_notify.token
        self.enabled = cfg.line_notify.enabled and bool(self.token)
        self.api = "https://notify-api.line.me/api/notify"

    def send(self, msg: str) -> bool:
        if not self.enabled:
            return False

        try:
            import requests
            r = requests.post(
                self.api,
                headers={"Authorization": f"Bearer {self.token}",
                         "Content-Type": "application/x-www-form-urlencoded"},
                data={"message": msg},
                timeout=10,
            )
            if r.status_code == 200:
                logger.info("LINE sent")
                return True
            logger.error(f"LINE error {r.status_code}")
            return False
        except Exception as e:
            logger.error(f"LINE failed: {e}")
            return False

    def alert(self, kind: str, msg: str) -> bool:
        return self.send(f"\n[{kind}] {msg}")

    def trade_signal(self, analysis) -> bool:
        if not self.enabled:
            return False
        lines = [
            "><> MAE PLA AUTO TRADER",
            f"XAUUSD ${analysis.price:.2f}",
            f"Decision: {analysis.decision}",
            f"Score: {analysis.total_score}/10 ({analysis.grade})",
            f"",
            f"Monthly: {analysis.monthly}",
            f"H4: {analysis.h4}",
            f"Grid: {analysis.grid_score_val}/2",
            f"ATH: {analysis.ath_pct}%",
            f"PA: {analysis.pa_overall}",
        ]
        if analysis.trade_plan:
            tp = analysis.trade_plan
            lines += [
                f"",
                f"Entry: ${tp['entry']:.2f}",
                f"SL: ${tp['sl']:.2f}",
                f"TP: ${tp['tp1']:.2f}",
                f"RR: {tp['rr']}:1",
                f"Reason: {tp['reason']}",
            ]
        lines.append("")
        lines.append("#MaePlaAuto #XAUUSD")
        return self.send("\n".join(lines))
