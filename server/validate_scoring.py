"""점수 재현 검증: 저장된 featv12_test 의 v11 특성 129열로 서버 score()를 돌려 pred_test_modelA_v11.parquet 의 p 와 비교."""
import json, sys
import numpy as np, pandas as pd
sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent))
import app
root = app.HERE.parent / "ML 개발"
feats = json.load(open(app.DATA / "features.json"))
t = pd.read_parquet(root / "v12" / "featv12_test.parquet", columns=["row_order"] + feats).sample(20000, random_state=0)
ref = pd.read_parquet(root / "v11" / "pred_test_modelA_v11.parquet", columns=["row_order", "p_modelA_v11"]).set_index("row_order")
p = app.score(app.load_model(), t[feats])
r = ref.loc[t["row_order"], "p_modelA_v11"].to_numpy()
print("행", len(t), "| 최대 절대차", float(np.abs(p - r).max()), "| 평균 절대차", float(np.abs(p - r).mean()))
