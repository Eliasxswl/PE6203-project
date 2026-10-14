"""Source selection must retain the exact callable name on current 1mcp."""
from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from mcp.types import Tool, ListToolsResult
from custom.utils.mcp_utils import normalize_1mcp_tools
from custom.real_mcp.tool_level_test import return_involved_tool_status

class RoutingTests(unittest.TestCase):
    def test_hashed_route_survives_task_selection(self):
        result = ListToolsResult(tools=[Tool(name='hashed_route', inputSchema={'type':'object'},
            description='Read a file', _meta={'app.1mcp/route':{
                'server':'files', 'upstreamIdentity':'read_text_file'}})])
        normalize_1mcp_tools(result)
        normalize_1mcp_tools(result)
        selected = return_involved_tool_status({'files':['read_text_file']}, result)
        self.assertEqual(selected[0]['name'], 'read_text_file')
        self.assertEqual(selected[0]['meta']['benchmark_remote_name'], 'hashed_route')

    def test_legacy_names_still_work(self):
        result = ListToolsResult(tools=[Tool(name='files_1mcp_read_text_file', inputSchema={}, description='Read')])
        normalize_1mcp_tools(result)
        selected = return_involved_tool_status({'files':['read_text_file']}, result)
        self.assertEqual(selected[0]['name'], 'read_text_file')

if __name__ == '__main__':
    unittest.main()
