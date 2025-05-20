import json
from collections import defaultdict

class JsonSchemaLoader:
    '''JSON 형식의 데이터 명세서를 변환하는 클래스'''
    def __init__(self, json_path):
        with open(json_path, 'r', encoding='utf-8') as f:
            self.raw_data = json.load(f)
        
        self.tables = {table['table_name']: table for table in self.raw_data['tables']}
        self._build_metadata()

    def _build_metadata(self):
        """JSON 파일의 데이터 명세서를 변환"""
        self.metadata = defaultdict(dict)
        
        for table in self.raw_data['tables']:
            table_name = table['table_name']
            self.metadata[table_name]['description'] = table.get('description', '')
            self.metadata[table_name]['columns'] = {}
            for col in table['columns']:
                col_info = {
                    'type': col['type'],
                    'description': f"{col.get('description', '')} {col.get('note', '')}",
                    'is_primary': '(PK)' in col['description'],
                    'is_foreign': '(FK)' in col['description']
                }
                
                self.metadata[table_name]['columns'][col['name']] = col_info
            
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