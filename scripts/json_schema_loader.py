import json
from collections import defaultdict
from utils import cache_result

class JsonSchemaLoader:
    def __init__(self, json_path):
        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                self.raw_data = json.load(f)
            self.tables = {table['table_name']: table for table in self.raw_data.get('tables', [])}
            self._build_metadata()
            self._build_relation_graph()
        except Exception as e:
            print(f"JSON 파일 로드 중 오류 발생: {str(e)}")
            self.raw_data = {"tables": []}
            self.tables = {}
            self.metadata = defaultdict(dict)
            self.relation_graph = defaultdict(set)

    def _build_metadata(self):
        """JSON 메타데이터 구축"""
        self.metadata = defaultdict(dict)
        for table in self.raw_data.get('tables', []):
            table_name = table.get('table_name', '')
            if not table_name:
                continue
            self.metadata[table_name]['description'] = table.get('description', '')
            self.metadata[table_name]['columns'] = {}
            for col in table.get('columns', []):
                col_info = {
                    'type': col.get('type', ''),
                    'description': f"{col.get('description', '')} {col.get('note', '')}".strip(),
                    'is_primary': '(PK)' in col.get('description', ''),
                    'is_foreign': '(FK)' in col.get('description', '')
                }
                self.metadata[table_name]['columns'][col['name']] = col_info

    def _build_relation_graph(self):
        """테이블 관계 그래프 구축"""
        self.relation_graph = defaultdict(set)
        for table, details in self.metadata.items():
            for col_info in details['columns'].values():
                if col_info['is_foreign']:
                    referred_table = col_info['description'].split('(FK)')[-1].strip()
                    if referred_table in self.metadata:
                        self.relation_graph[table].add(referred_table)
                        self.relation_graph[referred_table].add(table)

    @cache_result()
    def get_related_tables(self, keyword):
        """키워드 기반 관련 테이블 탐색"""
        related = []
        for table, details in self.metadata.items():
            if keyword in details['description']:
                related.append(table)
                continue
            for _, col_info in details['columns'].items():
                if keyword in col_info['description']:
                    related.append(table)
                    break
        return list(set(related))
