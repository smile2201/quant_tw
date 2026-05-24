"""
runner/parallel_runner.py
Runner：雙核 Mac 用序列跑，Colab 環境自動升級為多進程

雙核機器：multiprocessing 開銷 > 效益，用序列跑
Colab（2核以上）：自動切換 multiprocessing
"""
import os
import time
import pickle
import itertools
from pathlib import Path
from typing import Callable, Optional

from config.settings import RUNNER, IS_COLAB, BACKTEST

RESULTS_DIR = Path(os.path.dirname(os.path.dirname(__file__))) / "results"
RESULTS_DIR.mkdir(exist_ok=True)

CHECKPOINT_PATH = RESULTS_DIR / "grid_checkpoint.pkl"


class ParallelRunner:
    """
    參數網格搜索 Runner

    本機雙核：序列執行（避免 multiprocessing 開銷）
    Colab：multiprocessing，workers 從 config 讀
    """

    def __init__(self, workers: Optional[int] = None):
        self.workers = workers or RUNNER["workers"]
        self._use_mp = IS_COLAB and self.workers > 1
        print(f"  [runner] workers={self.workers}, multiprocessing={self._use_mp}")

    def run_grid(
        self,
        task_fn:    Callable,
        param_grid: dict,
        resume:     bool = True,
    ) -> list:
        """
        網格搜索

        Args:
            task_fn:    接收一個 dict 參數，回傳 dict 結果的函式
            param_grid: {"param_name": [v1, v2, ...], ...}
            resume:     是否從 checkpoint 繼續（預設 True）

        Returns:
            list of result dicts
        """
        # 展開所有參數組合
        keys   = list(param_grid.keys())
        combos = [dict(zip(keys, v)) for v in itertools.product(*param_grid.values())]
        total  = len(combos)
        print(f"  [runner] 共 {total} 組參數")

        # 讀 checkpoint
        results   = []
        start_idx = 0
        if resume and CHECKPOINT_PATH.exists():
            try:
                with open(CHECKPOINT_PATH, "rb") as f:
                    ckpt = pickle.load(f)
                results   = ckpt["results"]
                start_idx = ckpt["i"] + 1
                print(f"  [runner] 從 checkpoint 繼續，i={start_idx}")
            except Exception:
                pass

        if self._use_mp:
            results = self._run_multiprocess(task_fn, combos, results, start_idx)
        else:
            results = self._run_serial(task_fn, combos, results, start_idx)

        # 清除 checkpoint
        if CHECKPOINT_PATH.exists():
            CHECKPOINT_PATH.unlink()

        return results

    def _run_serial(self, task_fn, combos, results, start_idx) -> list:
        """序列執行（本機雙核預設）"""
        total = len(combos)
        for i in range(start_idx, total):
            params = combos[i]
            t0     = time.time()
            try:
                result = task_fn(params)
                result["params"] = params
                results.append(result)
            except Exception as e:
                print(f"  [runner] 第 {i} 組失敗: {e}")
                results.append({"params": params, "error": str(e)})

            elapsed = time.time() - t0
            print(f"  [{i+1}/{total}] {params} → {elapsed:.1f}s")

            # 每 10 組存 checkpoint
            if (i + 1) % 10 == 0:
                self._save_checkpoint(results, i)

        return results

    def _run_multiprocess(self, task_fn, combos, results, start_idx) -> list:
        """多進程執行（Colab 環境）"""
        import multiprocessing as mp

        total     = len(combos)
        remaining = combos[start_idx:]

        with mp.Pool(processes=self.workers) as pool:
            for i, result in enumerate(pool.imap(task_fn, remaining)):
                idx = start_idx + i
                result["params"] = combos[idx]
                results.append(result)
                print(f"  [{idx+1}/{total}] done")

                if (idx + 1) % 10 == 0:
                    self._save_checkpoint(results, idx)

        return results

    def _save_checkpoint(self, results, i):
        with open(CHECKPOINT_PATH, "wb") as f:
            pickle.dump({"results": results, "i": i}, f)
        print(f"  [checkpoint] saved at i={i}")

    def run_ablation(
        self,
        task_fn:    Callable,
        base_params: dict,
    ) -> dict:
        """
        Ablation 實驗：逐一關閉各模組，量化其貢獻

        Args:
            task_fn:     接收 params dict 的函式
            base_params: 基準參數（三模組全開）

        Returns:
            dict {experiment_name: result}
        """
        experiments = {
            "all":         {**base_params, "use_tech": True,  "use_fund": True,  "use_event": True},
            "no_tech":     {**base_params, "use_tech": False, "use_fund": True,  "use_event": True},
            "no_fund":     {**base_params, "use_tech": True,  "use_fund": False, "use_event": True},
            "no_event":    {**base_params, "use_tech": True,  "use_fund": True,  "use_event": False},
            "tech_only":   {**base_params, "use_tech": True,  "use_fund": False, "use_event": False},
            "fund_only":   {**base_params, "use_tech": False, "use_fund": True,  "use_event": False},
        }

        results = {}
        total   = len(experiments)
        for i, (name, params) in enumerate(experiments.items(), 1):
            print(f"  [ablation {i}/{total}] {name}")
            try:
                results[name] = task_fn(params)
            except Exception as e:
                results[name] = {"error": str(e)}

        return results
