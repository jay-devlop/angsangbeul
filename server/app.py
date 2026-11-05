"""추천 서버: 저장된 v11 모델(4개 + 스태킹)을 실제로 실행해 '기존 추천'과 '보정 추천' 순서를 돌려준다.
- 입력: data/pairs_features.parquet (장르별 데모 사용자 11명 x 웹곡 특성 129개), data/pop_ref.npy (인기도 백분위 기준)
- 모델: ../ML 개발/v11/ (수정하지 않음). 환경변수 MODEL_DIR 로 바꿀 수 있음
- 응답은 KKBox song_id 순서만. 점수·보정값·모델 이름은 내보내지 않는다 (기능정의서 D4)
실행: python3 app.py   (포트 8010, 환경변수 PORT)"""
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import joblib
import lightgbm  # noqa: F401  (joblib 로드에 필요)
import numpy as np
import pandas as pd
import xgboost  # noqa: F401
from catboost import CatBoostClassifier

HERE = Path(__file__).resolve().parent
MODEL_DIR = Path(os.environ.get("MODEL_DIR", HERE.parent / "ML 개발" / "v11"))
DATA = HERE / "data"
LAMBDA, TOPK = 0.20, 10          # 보고서의 일괄 보정(정책 2, 손실 한도 1%p): p - 0.20 x 인기도 백분위
CATS = ["primary_genre_code", "src_tab", "src_screen", "src_type"]


def logit(p):
    p = np.clip(np.asarray(p, dtype=float), 1e-6, 1 - 1e-6)
    return np.log(p / (1 - p))


def load_model():
    j = joblib.load(MODEL_DIR / "modelA_v11_models.joblib")
    cb = CatBoostClassifier()
    cb.load_model(str(MODEL_DIR / "modelA_v11_catboost.cbm"))
    assert j["chosen"] == "Stack4"
    return j, cb


def lgb_pred(m, X):
    return m.predict_proba(X, num_iteration=m.best_iteration_)[:, 1] if m.best_iteration_ else m.predict_proba(X)[:, 1]


def score(model, X):
    """특성 행렬 X(129열, 학습 때 순서) -> 재청취 확률 p"""
    j, cb = model
    P = {
        "LightGBM": np.mean([lgb_pred(m, X) for m in j["models"]["LightGBM"]], axis=0),
        "LightGBM_B": np.mean([lgb_pred(m, X) for m in j["models"]["LightGBM_B"]], axis=0),
        "CatBoost": cb.predict_proba(X)[:, 1],
        "XGBoost": j["models"]["XGBoost"].predict_proba(X)[:, 1],
    }
    return j["meta"].predict_proba(np.column_stack([logit(P[n]) for n in ["LightGBM", "LightGBM_B", "CatBoost", "XGBoost"]]))[:, 1]


def popularity_pct(ref, s_cnt_now):
    return np.searchsorted(ref, np.log1p(np.asarray(s_cnt_now, dtype=float))) / len(ref)


def rank_lists(p, pct, song_ids):
    base = np.argsort(-p, kind="stable")[:TOPK]
    adj = np.argsort(-(p - LAMBDA * pct), kind="stable")[:TOPK]
    return [song_ids[i] for i in base], [song_ids[i] for i in adj]


def merge_lists(lists, k=TOPK):
    """장르 사용자 여러 명(회원가입 장르 최대 3개)의 추천을 번갈아 한 곡씩 가져와 합침 (중복 제외)"""
    out, seen = [], set()
    for i in range(max((len(l) for l in lists), default=0)):
        for l in lists:
            if i < len(l) and l[i] not in seen:
                seen.add(l[i]); out.append(l[i])
                if len(out) == k:
                    return out
    return out


def prepare():
    model = load_model()
    feats = json.load(open(DATA / "features.json"))
    pf = pd.read_parquet(DATA / "pairs_features.parquet")
    ref = np.load(DATA / "pop_ref.npy")
    out = {}
    for u, g in pf.groupby("user"):
        g = g.reset_index(drop=True)
        p = score(model, g[feats])
        out[u] = rank_lists(p, popularity_pct(ref, g["s_cnt_now"]), g["song_id"].tolist())
    return model, out, feats, pf, ref


class App:
    def __init__(self):
        self.model, self.recs, self.feats, self.pf, self.ref = prepare()   # 모델 실행 결과는 시작 때 계산해 둠
        self.profiles = json.load(open(DATA / "demo_profiles.json", encoding="utf-8"))


def make_handler(app):
    class H(BaseHTTPRequestHandler):
        def _send(self, code, obj):
            body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")   # 웹(다른 포트)에서 호출
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_OPTIONS(self):
            self._send(204, {})

        def do_GET(self):
            u = urlparse(self.path)
            if u.path == "/api/users":
                return self._send(200, app.profiles)
            if u.path == "/api/recommend":
                # genres=팝,힙합,재즈 : 회원가입에서 고른 장르(알 수 없는 이름은 무시)
                names = [g for g in ((parse_qs(u.query).get("genres") or [""])[0].split(",")) if g in app.recs][:3]
                if not names:
                    return self._send(404, {"error": "no known genre"})
                return self._send(200, {"genres": names,
                                        "base": merge_lists([app.recs[g][0] for g in names]),
                                        "adjusted": merge_lists([app.recs[g][1] for g in names])})
            self._send(404, {"error": "not found"})

        def log_message(self, *a):
            pass
    return H


if __name__ == "__main__":
    app = App()
    port = int(os.environ.get("PORT", 8010))
    print(f"추천 서버 준비 완료: 사용자 {list(app.recs)} | http://localhost:{port}/api/users", flush=True)
    ThreadingHTTPServer(("0.0.0.0", port), make_handler(app)).serve_forever()
