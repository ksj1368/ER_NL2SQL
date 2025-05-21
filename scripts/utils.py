import hashlib
import time
import functools

def cache_result(expires_after=3600):  # 기본 1시간 캐싱
    '''함수 실행 결과 캐싱하는 함수'''
    cache = {}
    
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            # 함수 호출 정보로 캐시 키 생성
            key = hashlib.md5(str((func.__name__, args, kwargs)).encode()).hexdigest()
            
            # 캐시된 결과가 있고 만료되지 않았으면 반환
            if key in cache and time.time() - cache[key]['time'] < expires_after:
                return cache[key]['result']
            
            # 함수 실행 및 결과 캐싱
            result = func(*args, **kwargs)
            cache[key] = {'result': result, 'time': time.time()}
            return result
        return wrapper
    return decorator