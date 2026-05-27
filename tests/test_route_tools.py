import unittest

from reverse_deepagent.schemas import ReverseMode, ReverseStage
from reverse_deepagent.tools.route_tools import normalize_task_card, route_from_task_card


class RouteToolsTests(unittest.TestCase):
    def test_normalize_task_card_from_freeform_text(self) -> None:
        task_text = """
        target_url_or_file: https://example.com/search
        target_param_or_api: x-sign
        goal: 找到 x-sign 的生成入口
        boundaries: 不登录，不做破坏性操作
        sample_request: POST /api/search
        protection_hints: debugger, webpack
        """
        task_card = normalize_task_card(task_text)
        self.assertEqual(task_card.target_url_or_file, "https://example.com/search")
        self.assertEqual(task_card.target_param_or_api, "x-sign")
        self.assertIn("webpack", task_card.protection_hints)

    def test_route_from_task_card_uses_intent_and_start_stage(self) -> None:
        task_card = normalize_task_card("https://example.com/search 找 sign 入口")
        result = route_from_task_card(task_card, task_text="帮我找 sign 入口并定位签名函数")
        self.assertEqual(result.selected_mode, ReverseMode.FIND_ENTRY)
        self.assertEqual(result.initial_stage, ReverseStage.NETWORK)
        self.assertEqual(result.next_action, "delegate_to_web_recon")


if __name__ == "__main__":
    unittest.main()
