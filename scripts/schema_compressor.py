from collections import defaultdict

class SchemaCompressor:
    def __init__(self, schema_info, json_loader):
        self.schema_info = schema_info
        self.json_loader = json_loader
        
    def _filter_columns(self, table_name, columns):
        """JSON 메타데이터 기반 컬럼 필터링"""
        important_cols = []
        metadata = self.json_loader.metadata.get(table_name, {})
        
        for col in columns:
            col_name = col['name']
            col_meta = metadata.get('columns', {}).get(col_name, {})
            if col_meta.get('is_primary') or col_meta.get('is_foreign'):
                important_cols.append(col)
            elif '검색빈도' in col_meta.get('note', ''):
                important_cols.append(col)
        return important_cols if important_cols else columns
    
    def _find_common_prefixes(self, names):
        prefix_groups = defaultdict(list)
        for name in names:
            parts = name.split('_')
            if len(parts) > 1:
                prefix = parts[0]
                prefix_groups[prefix].append(name)
        return prefix_groups

    def generate_compressed_prompt(self, filtered_tables): 
        prompt = []
        
        # 필터링된 테이블만 처리
        for table_name in filtered_tables:
            details = self.schema_info[table_name]
            
            # 컬럼 압축
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