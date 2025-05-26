import numpy as np
from sentence_transformers import SentenceTransformer
import faiss
import json

class SchemaEmbedder:
    def __init__(self, json_loader):
        self.model = SentenceTransformer(
            'sentence-transformers/paraphrase-multilingual-mpnet-base-v2',
            device='cpu'
        )
        self.json_loader = json_loader
        self.table_index = None
        self.column_index = None
        self.table_data = []
        self.column_data = []
        faiss.omp_set_num_threads(4)

    def _generate_table_descriptions(self):
        """테이블 레벨 설명문 생성"""
        schema = self.json_loader.metadata
        
        for table, details in schema.items():
            table_desc = details['description']
            
            # 외래키 관계 정보 추가
            fk_relations = []
            for col, col_info in details['columns'].items():
                if '(FK)' in col_info['description']:
                    referred_table = col_info['description'].split('(FK)')[-1].strip()
                    fk_relations.append(f"{col} → {referred_table}")
            
            # 주요 컬럼 요약
            key_columns = []
            for col, col_info in details['columns'].items():
                if any(kw in col_info['description'] for kw in ['PK', 'FK', '키', '식별자']):
                    key_columns.append(f"{col}: {col_info['description']}")
            
            full_desc = (
                f"테이블: {table}\n"
                f"설명: {table_desc}\n"
                f"주요 컬럼: {', '.join(key_columns[:5])}\n"  # 상위 5개만
                f"관계: {', '.join(fk_relations)}"
            )
            
            self.table_data.append((table, full_desc))

    def _generate_column_descriptions(self):
        """컬럼 레벨 설명문 생성"""
        schema = self.json_loader.metadata
        
        for table, details in schema.items():
            table_desc = details['description']
            
            for col, col_info in details['columns'].items():
                col_desc = (
                    f"테이블: {table} ({table_desc})\n"
                    f"컬럼: {col}\n"
                    f"설명: {col_info['description']}\n"
                    f"타입: {col_info.get('type', '')}"
                )
                
                if col_info.get('note'):
                    col_desc += f"\n참고: {col_info['note']}"
                
                self.column_data.append((table, col, col_desc))

    def build_index(self):
        """FAISS 인덱스 구축 (테이블 및 컬럼 별도)"""
        # 테이블 레벨 인덱스
        self._generate_table_descriptions()
        table_texts = [desc[1] for desc in self.table_data]
        table_embeddings = self.model.encode(table_texts, convert_to_numpy=True)
        
        table_dimension = table_embeddings.shape[1]
        self.table_index = faiss.IndexFlatL2(table_dimension)
        self.table_index.add(table_embeddings.astype('float32'))
        
        # 컬럼 레벨 인덱스
        self._generate_column_descriptions()
        column_texts = [desc[2] for desc in self.column_data]
        column_embeddings = self.model.encode(column_texts, convert_to_numpy=True)
        
        column_dimension = column_embeddings.shape[1]
        self.column_index = faiss.IndexFlatL2(column_dimension)
        self.column_index.add(column_embeddings.astype('float32'))

    def search_tables(self, query, k=5):
        """테이블 레벨 검색"""
        query_embedding = self.model.encode([query], convert_to_numpy=True)
        distances, indices = self.table_index.search(query_embedding.astype('float32'), k)
        
        results = []
        for idx, distance in zip(indices[0], distances[0]):
            table, desc = self.table_data[idx]
            results.append({
                'table': table,
                'description': desc,
                'similarity_score': float(1 / (1 + distance))  # 거리를 유사도로 변환
            })
        
        return results

    def search_columns(self, query, k=10):
        """컬럼 레벨 검색"""
        query_embedding = self.model.encode([query], convert_to_numpy=True)
        distances, indices = self.column_index.search(query_embedding.astype('float32'), k)
        
        results = []
        for idx, distance in zip(indices[0], distances[0]):
            table, column, desc = self.column_data[idx]
            results.append({
                'table': table,
                'column': column,
                'description': desc,
                'similarity_score': float(1 / (1 + distance))
            })
        
        return results

    def search_schema(self, query, table_k=3, column_k=5):
        """통합 스키마 검색 (테이블 + 컬럼)"""
        table_results = self.search_tables(query, table_k)
        column_results = self.search_columns(query, column_k)
        
        # 테이블 단위로 정리
        table_columns = {}
        
        # 테이블 레벨 결과 추가
        for result in table_results:
            table = result['table']
            if table not in table_columns:
                table_columns[table] = {
                    'table_score': result['similarity_score'],
                    'columns': []
                }
        
        # 컬럼 레벨 결과 추가
        for result in column_results:
            table = result['table']
            if table not in table_columns:
                table_columns[table] = {
                    'table_score': 0.0,
                    'columns': []
                }
            
            table_columns[table]['columns'].append({
                'column': result['column'],
                'score': result['similarity_score']
            })
        
        return table_columns
