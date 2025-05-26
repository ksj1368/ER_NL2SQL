import os
import json
import re
from sqlalchemy import create_engine, inspect
from dotenv import load_dotenv
from collections import defaultdict
class SchemaMapper:
    def __init__(self, connection_string, schema_json_path):
        self.engine = create_engine(connection_string)
        self.inspector = inspect(self.engine)
        self.base_path = "mapping"
        os.makedirs(self.base_path, exist_ok=True)
        
        # JSON 스키마 로드
        with open(schema_json_path, 'r', encoding='utf-8') as f:
            self.schema_data = json.load(f)
        
        self._init_metadata_templates()
        
    def _init_metadata_templates(self):
        """메타데이터 템플릿 초기화"""
        self.metadata_types = {
            'table': {
                'description': '',
                'business_terms': [],
                'common_queries': []
            },
            'column': {
                'description': '',
                'data_type': '',
                'business_rules': []
            }
        }
        
    def _extract_kr_en_mappings(self):
        """JSON 기반 한영 매핑 추출"""
        kr_en_map = {}
        
        for table in self.schema_data['tables']:
            # 테이블명 매핑
            if 'description' in table:
                kr, en = self._split_kr_en(table['description'])
                kr_en_map[kr.lower()] = en.lower()
            
            # 컬럼명 매핑
            for col in table['columns']:
                if 'description' in col:
                    kr, en = self._split_kr_en(col['description'])
                    kr_en_map[kr.lower()] = en.lower()
                    
        return kr_en_map

    def _split_kr_en(self, text):
        """한영 분리 헬퍼 함수"""
        if ':' in text:
            return map(str.strip, text.split(':', 1))
        return text, text  # 기본값

    def _extract_enhanced_metadata(self):
        """JSON 기반 확장 메타데이터 생성"""
        metadata = {'tables': {}, 'relationships': []}
        
        for table in self.schema_data['tables']:
            table_name = table['table_name']
            metadata['tables'][table_name] = {
                'description': self._parse_table_comment(table),
                'columns': {},
                'foreign_keys': self._extract_foreign_keys(table)
            }
            
            # 컬럼 메타데이터
            for col in table['columns']:
                metadata['tables'][table_name]['columns'][col['name']] = {
                    'description': col.get('description', ''),
                    'business_terms': self._parse_business_rules(col),
                    'data_type': col['type']
                }
                
        return metadata

    def _parse_table_comment(self, table):
        """테이블 주석 파싱"""
        return table.get('description', '').split(':')[-1].strip()

    def _parse_business_rules(self, column):
        """비즈니스 규칙 추출"""
        rules = []
        if 'note' in column:
            rules = [r.strip() for r in column['note'].split('(')[-1].replace(')', '').split(',')]
        return rules

    def _extract_foreign_keys(self, table):
        """외래키 관계 추출"""
        fks = []
        for col in table['columns']:
            if 'FK' in col.get('description', ''):
                ref_table = col['description'].split('(FK)')[-1].strip()
                fks.append({
                    'constrained_columns': [col['name']],
                    'referred_table': ref_table
                })
        return fks
    def _parse_column_comment(self, comment):
        """컬럼 코멘트 파싱 (RAG 문서화 표준)"""
        result = {'description': '', 'terms': []}
        if not comment:
            return result
            
        # 구조: [한글명]: [영문명] - [설명] (비즈니스 규칙: [규칙])
        if '비즈니스 규칙:' in comment:
            desc_part, rule_part = comment.split('비즈니스 규칙:', 1)
            result['description'] = desc_part.split('-', 1)[-1].strip()
            result['terms'] = [r.strip() for r in rule_part.split(';')]
        elif '-' in comment:
            result['description'] = comment.split('-', 1)[-1].strip()
        return result

    def _detect_table_aliases(self):
        """개선된 테이블 별칭 감지 로직"""
        # 기존 로직 유지
        tables = self.inspector.get_table_names()
        alias_map = {}
        prefix_groups = defaultdict(list)

        for table in tables:
            parts = table.split('_')
            if len(parts) > 1:
                prefix = '_'.join(parts[:-1])
                prefix_groups[prefix].append(table)

        for prefix, group in prefix_groups.items():
            if len(group) > 1:
                base_table = max(group, key=len)
                for table in group:
                    if table != base_table:
                        alias_map[prefix] = base_table
        
        return alias_map
    
    def generate_mappings(self):
        """확장된 메타데이터 생성 및 저장"""
        # 매핑
        kr_en = self._extract_kr_en_mappings()
        aliases = self._detect_table_aliases()
        enhanced_meta = self._extract_enhanced_metadata()

        # 파일 저장
        with open(os.path.join(self.base_path, 'rag_metadata.json'), 'w', encoding='utf-8') as f:
            json.dump(enhanced_meta, f, ensure_ascii=False, indent=2)

        with open(os.path.join(self.base_path, 'kr_en_mapping.json'), 'w', encoding='utf-8') as f:
            json.dump(kr_en, f, ensure_ascii=False, indent=2)

        with open(os.path.join(self.base_path, 'table_aliases.json'), 'w', encoding='utf-8') as f:
            json.dump(aliases, f, ensure_ascii=False, indent=2)

        print("mapping 파일이 성공적으로 생성되었습니다.")

if __name__ == "__main__":
    load_dotenv()
    
    # 데이터베이스 연결 설정
    db_config = {
        "host": os.getenv("DB_HOST"),
        "user": os.getenv("DB_USER"),
        "password": os.getenv("DB_PASSWORD"),
        "database": os.getenv("DB_NAME"),
        "port": os.getenv("DB_PORT")
    }
    
    # JSON 스키마 경로 지정
    schema_json_path = "./docs/data_discription.json"
    
    connection_string = (
        f"mysql+pymysql://{db_config['user']}:{db_config['password']}"
        f"@{db_config['host']}:{db_config['port']}/{db_config['database']}"
    )
    
    # 매퍼 초기화
    mapper = SchemaMapper(
        connection_string=connection_string,
        schema_json_path=schema_json_path
    )
    mapper.generate_mappings()