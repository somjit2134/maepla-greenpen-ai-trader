import requests
from typing import Optional

from src.config_loader import get_config
from src.log_setup import get_logger

logger = get_logger()


class LINENotifier:
    def __init__(self, token: Optional[str] = None):
        cfg = get_config()
        self.token = token or cfg.line_notify.token
        self.enabled = cfg.line_notify.enabled and bool(self.token)
        self.api_url = "https://notify-api.line.me/api/notify"

    def send(self, message: str) -> bool:
        if not self.enabled:
            logger.debug("LINE notification disabled")
            return False

        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/x-www-form-urlencoded",
        }

        try:
            response = requests.post(
                self.api_url,
                headers=headers,
                data={"message": message},
                timeout=10,
            )

            if response.status_code == 200:
                logger.info("LINE notification sent")
                return True
            else:
                logger.error(f"LINE API error: {response.status_code} - {response.text}")
                return False

        except requests.RequestException as e:
            logger.error(f"LINE notification failed: {e}")
            return False

    def send_analysis(self, analysis_result) -> bool:
        if not self.enabled:
            return False

        fish = "><>"
        msg = (
            f"\\n{fish} MAE PLA GREEN PEN AI\\n"
            f"========================\\n"
            f"XAUUSD | ${analysis_result.current_price:.2f}\\n"
            f"Decision: {analysis_result.final_decision}\\n"
            f"\\n"
            f"Monthly: {analysis_result.monthly_bias}\\n"
            f"H4: {analysis_result.h4_structure}\\n"
            f"Position: {analysis_result.current_position}\\n"
            f"\\n"
        )

        if analysis_result.trade_plan:
            tp = analysis_result.trade_plan
            msg += (
                f"TRADE PLAN\\n"
                f"Direction: {tp.get('direction')}\\n"
                f"Entry: ${tp.get('entry', 0):.2f}\\n"
                f"SL: ${tp.get('stop_loss', 0):.2f}\\n"
                f"TP1: ${tp.get('take_profit_1', 0):.2f}\\n"
                f"RR: {tp.get('risk_reward', 0)}:1\\n"
            )
        else:
            msg += "No active setup. Waiting."

        if analysis_result.buy_score:
            msg += f"\\nBuy Score: {analysis_result.buy_score.total}/10"
        if analysis_result.sell_score:
            msg += f"\\nSell Score: {analysis_result.sell_score.total}/10"

        msg += "\\n========================\\n#MaePlaGreenPen #XAUUSD"

        return self.send(msg)

    def send_alert(self, title: str, body: str) -> bool:
        return self.send(f"\\n{title}\\n{body}")
