import re
from collections import defaultdict
import itertools

class SchemaCompressor:
    def __init__(self, schema_info):
        self.schema_info = schema_info
        self.prefix_map = {}

    def _find_common_prefixes(self, names):
        prefix_groups = defaultdict(list)
        for name in names:
            parts = name.split('_')
            if len(parts) > 1:
                prefix = parts[0]
                prefix_groups[prefix].append(name)
        return prefix_groups

    def generate_compressed_prompt(self, filtered_tables):  # 인자 추가
        prompt = []
        TABLE_ALIAS_MAP = {
            'match_user': 'match_user_basic',
            'user': 'match_user_basic',
            'match': 'match_info'
        }
        
        # 필터링된 테이블만 처리
        for table_name in filtered_tables:
            actual_name = TABLE_ALIAS_MAP.get(table_name.lower(), table_name)
            # details = self.schema_info[table_name]
            details = self.schema_info[actual_name]
            
            # 컬럼 압축 로직
            columns = [col['name'] for col in details['columns']]
            prefix_groups = self._find_common_prefixes(columns)
            
            table_compressed = []
            for prefix, group in prefix_groups.items():
                if len(group) > 2:
                    self.prefix_map[prefix] = group
                    table_compressed.append(f"{prefix}_*")
                else:
                    table_compressed.extend(group)
            
            # 테이블 설명 생성
            table_desc = f"Table: {table_name}\nColumns:\n"
            table_desc += "\n".join(f" - {col}" for col in table_compressed)
            
            # 관계 정보 추가
            if details['foreign_keys']:
                table_desc += "\nForeign Keys:\n"
                for fk in details['foreign_keys']:
                    src_cols = ", ".join(fk['constrained_columns'])
                    ref_cols = ", ".join(fk['referred_columns'])
                    table_desc += f" - {src_cols} → {fk['referred_table']}.{ref_cols}\n"
            
            prompt.append(table_desc)
        return "\n\n".join(prompt)