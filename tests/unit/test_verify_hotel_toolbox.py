import io
import json
import unittest
from unittest import mock

from verify_hotel_toolbox import (
    ToolboxClient,
    main,
    read_rpc_response,
    validate_tools,
    weather_arguments,
    web_result_count,
)


def web_schema() -> dict[str, object]:
    return {
        "type": "object",
        "required": ["query"],
        "properties": {
            name: {"type": kind, "properties": {}, "required": []}
            for name, kind in (
                ("query", "string"),
                ("maxResults", "integer"),
                ("contentFormat", "string"),
                ("maxLength", "integer"),
                ("safeSearch", "string"),
            )
        },
    }


class VerifyHotelToolboxTests(unittest.TestCase):
    def test_sse_skips_notifications_and_matches_response_id(self) -> None:
        stream = io.BytesIO(
            b'data: {"jsonrpc":"2.0","method":"notifications/progress"}\n\n'
            b'event: message\ndata: {"jsonrpc":"2.0","id":2,\n'
            b'data: "result":{"tools":[]}}\n\n'
        )
        self.assertEqual(read_rpc_response(stream, "text/event-stream", 2)["result"], {"tools": []})

    def test_json_response_requires_matching_id(self) -> None:
        with self.assertRaisesRegex(ValueError, "ID does not match"):
            read_rpc_response(io.BytesIO(b'{"id":1,"result":{}}'), "application/json", 2)

    def test_inventory_requires_each_actual_iq_namespace(self) -> None:
        tools = [
            {"name": f"{prefix}.read", "inputSchema": {"properties": {}}}
            for prefix in ("foundry", "fabric", "work", "web")
        ]
        self.assertEqual(len(validate_tools(tools, ("foundry", "fabric", "work", "web"))), 4)
        with self.assertRaisesRegex(ValueError, "no discovered tools for web"):
            validate_tools(tools[:3], ("foundry", "fabric", "work", "web"))

    def test_web_results_accept_adjacent_pretty_printed_json(self) -> None:
        text = json.dumps({"webResults": [{"content": "not retained"}]}, indent=2)
        text += "\n" + json.dumps({"structuredResponse": {}}, indent=2)
        self.assertEqual(web_result_count({"content": [{"type": "text", "text": text}]}), 1)

    def test_web_error_is_not_success(self) -> None:
        with self.assertRaisesRegex(ValueError, "tool error"):
            web_result_count({"isError": True, "content": [{"type": "text", "text": "error"}]})

    def test_weather_probe_validates_advertised_string_and_integer_schema(self) -> None:
        arguments = weather_arguments({"inputSchema": web_schema()})
        self.assertIsInstance(arguments["query"], str)
        self.assertIsInstance(arguments["maxResults"], int)
        self.assertIsInstance(arguments["maxLength"], int)

    def test_weather_probe_rejects_changed_input_types_before_calling(self) -> None:
        for field, wrong_type in (("query", "integer"), ("maxLength", "string")):
            with self.subTest(field=field):
                schema = web_schema()
                properties = schema["properties"]
                assert isinstance(properties, dict)
                properties[field] = {"type": wrong_type}
                with self.assertRaisesRegex(ValueError, f"Web IQ {field} schema"):
                    weather_arguments({"inputSchema": schema})

    def test_weather_probe_requires_query_in_advertised_required_fields(self) -> None:
        schema = web_schema()
        schema["required"] = []
        with self.assertRaisesRegex(ValueError, "must require query"):
            weather_arguments({"inputSchema": schema})

    def test_bearer_token_cannot_be_sent_to_untrusted_endpoint(self) -> None:
        with self.assertRaisesRegex(ValueError, "trusted Foundry"):
            ToolboxClient("https://example.test/toolboxes/hotel/mcp", "test-token")

    def test_initialize_sends_the_required_notification(self) -> None:
        client = ToolboxClient(
            "https://test.services.ai.azure.com/api/projects/test/toolboxes/test/mcp",
            "test-token",
        )
        with (
            mock.patch.object(client, "rpc", return_value={"protocolVersion": "2025-03-26"}),
            mock.patch.object(client, "post") as post,
        ):
            client.initialize()
        post.assert_called_once_with(
            {"jsonrpc": "2.0", "method": "notifications/initialized"}, None
        )

    def test_live_probe_is_weather_only_and_does_not_print_content_or_token(self) -> None:
        prefixes = ("foundry", "fabric", "work", "web")
        tools = [
            {"name": f"{prefix}.web", "inputSchema": {"properties": {}}} for prefix in prefixes
        ]
        tools[-1]["inputSchema"] = web_schema()
        args = [
            "verify_hotel_toolbox",
            "--endpoint",
            "https://test.services.ai.azure.com/api/projects/test/toolboxes/test/mcp",
            "--subscription",
            "test-subscription",
            "--web-tool",
            "web.web",
        ]
        for prefix in prefixes:
            args.extend(("--expect-prefix", prefix))
        stdout = io.StringIO()
        with (
            mock.patch("sys.argv", args),
            mock.patch("shutil.which", return_value="az"),
            mock.patch("subprocess.run", return_value=mock.Mock(returncode=0, stdout="test-token")),
            mock.patch("verify_hotel_toolbox.ToolboxClient") as factory,
            mock.patch("sys.stdout", stdout),
        ):
            client = factory.return_value
            client.rpc.side_effect = [
                {"tools": tools},
                {"structuredContent": {"webResults": [{"content": "not retained"}]}},
            ]
            main()
        query = client.rpc.call_args.args[1]["arguments"]["query"]
        self.assertIn("weather", query.lower())
        self.assertNotIn("documentation", query.lower())
        self.assertNotIn("test-token", stdout.getvalue())
        self.assertNotIn("not retained", stdout.getvalue())


if __name__ == "__main__":
    unittest.main()
