import streamlit as st
import pandas as pd
import locale
import copy
import time
import random
from math import ceil
locale.setlocale(locale.LC_ALL, '')

st.set_page_config(page_title="Cutting Stock Optimizer", layout="wide")

lang = st.radio("🌐 表示言語 / Ngôn ngữ hiển thị", ["日本語", "Tiếng Việt"], horizontal=True)

TEXT = {
    "日本語": {
        "title": "共取り最適化ツール",
        "param": "パラメーター入力",
        "material_width": "材料幅 (mm)",
        "edge_loss": "両端ロス (mm)",
        "blade_width": "刃幅 (mm)",
        "demand_input": "作業指示の入力",
        "demand_count": "作業指示数",
        "cut_width": "カット幅",
        "cut_length": "必要長さ (M)",
        "stock_input": "材料ストックの入力",
        "stock_count": "材料ロール数",
        "roll_width": "ロール幅 (mm)",
        "roll_length": "ロール巻長 (M)",
        "roll_quantity": "ロール本数",
        "exec": "最適化実行",
        "result": "結果出力",
        "feedback": "作業指示へのフィードバック",
        "no_leftover": "端数なく最適化されています。",
        "leftover_msg": "以下のサイズについて端材があります：",
        "download": "結果CSVダウンロード",
        "use_advanced": "高度な再配置ロジックを使用する"
    },
    "Tiếng Việt": {
        "title": "Công cụ tối ưu hóa chung",
        "param": "Nhập tham số",
        "material_width": "Chiều rộng vật liệu (mm)",
        "edge_loss": "Hao hụt đầu/cuối (mm)",
        "blade_width": "Độ dày dao cắt (mm)",
        "demand_input": "Nhập yêu cầu cắt",
        "demand_count": "Số yêu cầu cắt",
        "cut_width": "Chiều rộng cắt",
        "cut_length": "Chiều dài cần thiết (M)",
        "stock_input": "Nhập tồn kho vật liệu",
        "stock_count": "Số cuộn vật liệu",
        "roll_width": "Chiều rộng cuộn (mm)",
        "roll_length": "Chiều dài cuộn (M)",
        "roll_quantity": "Số lượng cuộn",
        "exec": "Tối ưu hóa",
        "result": "Kết quả",
        "feedback": "Phản hồi cho yêu cầu cắt",
        "no_leftover": "Không có vật liệu thừa - tối ưu hóa hoàn toàn",
        "leftover_msg": "Có vật liệu thừa như sau:",
        "download": "Tải kết quả CSV",
        "use_advanced": "Sử dụng thuật toán bố trí nâng cao"
    }
}

T = TEXT[lang]
FEEDBACK_HEADER = {"日本語": "フィードバック", "Tiếng Việt": "Phản hồi"}
TABLE_HEADERS = {
    "日本語": ["幅", "巻長", "カット数", "割付", "残り幅", "使用量", "残量", "フィードバック"],
    "Tiếng Việt": ["Chiều rộng", "Chiều dài cuộn", "Số lần cắt", "Bố trí", "Phần dư", "Sản lượng", "Còn lại", "Phản hồi"]
}

st.title(T["title"])
use_advanced = st.checkbox(T["use_advanced"])

st.header(T["param"])
material_width = st.number_input(T["material_width"], value=1000.0, step=0.1, format="%.1f")
edge_loss = st.number_input(T["edge_loss"], value=10.0, step=0.1, format="%.1f")
blade_width = st.number_input(T["blade_width"], value=0.0, step=0.1, format="%.1f")

st.header(T["demand_input"])
demand_count = st.number_input(T["demand_count"], min_value=1, value=3, step=1)
demands = []
for i in range(demand_count):
    c1, c2 = st.columns(2)
    width = c1.number_input(f"{T['cut_width']} {i+1} (mm)", value=100.0, step=0.1, format="%.1f")
    length = c2.number_input(f"{T['cut_length']} {i+1}", value=1000)
    demands.append({"width": width, "length": length})

st.header(T["stock_input"])
stock_count = st.number_input(T["stock_count"], min_value=1, value=3, step=1)
stock = []
for i in range(stock_count):
    c1, c2, c3 = st.columns(3)
    w = c1.number_input(f"{T['roll_width']} {i+1}", value=1000.0, step=0.1, format="%.1f")
    l = c2.number_input(f"{T['roll_length']} {i+1}", value=50)
    q = c3.number_input(f"{T['roll_quantity']} {i+1}", value=1)
    for _ in range(q):
        stock.append({"width": w, "length": l, "used": False})

def assign_rolls(demands, stock, edge_loss, blade_width):
    demand_needs = copy.deepcopy(demands)
    # ✅ 優先順位: 1.幅が狭い 2.巻き数が少ない 3.幅が広い
    # まず幅でソート（昇順）、次に長さでソート（昇順）
    sorted_stock = sorted(stock, key=lambda x: (x["width"], x["length"]))
    results = []

    for roll in sorted_stock:
        remain_w = roll["width"] - edge_loss
        layout = []

        # ✅ 幅が広いものから優先
        for d in sorted(demand_needs, key=lambda x: x["width"], reverse=True):
            w = d["width"]
            while d["length"] > 0 and remain_w >= w + blade_width:
                layout.append(w)
                remain_w -= (w + blade_width)
                d["length"] -= roll["length"]

        results.append({
            "width": roll["width"],
            "length": roll["length"],
            "cuts": len(layout),
            "layout": layout,
            "remain": remain_w
        })

    return results

# ✅ 数理最適化による再配置ロジック（不足禁止、端材最大化、同一幅優先）

from ortools.linear_solver import pywraplp

def optimize_last_roll(results, edge_loss, blade_width, demands):
    if len(results) < 2:
        return results

    # 使用されているロールのみを対象とする
    used_results = [r for r in results if r["layout"]]
    if len(used_results) < 2:
        return results

    # 最も幅が広く、巻長が長いロールを特定（使用済みロールの中から）
    target_index = -1
    max_score = -1
    for idx, r in enumerate(results):
        if r["layout"]:  # 使用されているロールのみ
            score = r["width"] * 1000 + r["length"]
            if score > max_score:
                max_score = score
                target_index = idx
    
    if target_index == -1:
        return results

    # 基本割り当てで使用されたロールのみを最適化対象とする
    optimization_rolls = []
    for idx, r in enumerate(results):
        if r["layout"]:  # 使用されているロールのみ
            optimization_rolls.append({
                "width": r["width"],
                "length": r["length"],
                "original_idx": idx,
                "is_target": (idx == target_index)
            })
    
    # 必要な総長さを計算（元の需要量）
    total_demand_length = {}
    for d_id, d in enumerate(demands):
        total_demand_length[d_id] = d["length"]
    
    num_rolls = len(optimization_rolls)
    num_demands = len(demands)
    
    solver = pywraplp.Solver.CreateSolver("SCIP")
    if not solver:
        return results

    # 決定変数：x[i,j,k] = ロールjにdemand iをk本配置
    max_cuts_per_roll = 50
    x = {}
    for i in range(num_demands):
        for j in range(num_rolls):
            max_possible = int((optimization_rolls[j]["width"] - edge_loss) // (demands[i]["width"] + blade_width)) + 1
            max_k = min(max_cuts_per_roll, max_possible)
            for k in range(max_k + 1):
                x[i, j, k] = solver.IntVar(0, 1, f"x_{i}_{j}_{k}")
    
    # 各ロールで選択できるカット数は1つだけ
    for i in range(num_demands):
        for j in range(num_rolls):
            solver.Add(solver.Sum([x[i, j, k] for k in range(max_cuts_per_roll + 1) if (i, j, k) in x]) <= 1)
    
    # ロール幅制約
    for j in range(num_rolls):
        total_width = solver.Sum([
            x[i, j, k] * k * (demands[i]["width"] + blade_width)
            for i in range(num_demands)
            for k in range(1, max_cuts_per_roll + 1)
            if (i, j, k) in x
        ])
        solver.Add(total_width <= optimization_rolls[j]["width"] - edge_loss + blade_width)
    
    # 需要制約：各demandの必要長さを満たす
    for i in range(num_demands):
        total_length = solver.Sum([
            x[i, j, k] * k * optimization_rolls[j]["length"]
            for j in range(num_rolls)
            for k in range(1, max_cuts_per_roll + 1)
            if (i, j, k) in x
        ])
        solver.Add(total_length >= total_demand_length[i])
    
    # 同一幅カットを評価する補助変数
    y = {}
    for i in range(num_demands):
        for j in range(num_rolls):
            y[i, j] = solver.IntVar(0, 1, f"y_{i}_{j}")
            used = solver.Sum([x[i, j, k] for k in range(1, max_cuts_per_roll + 1) if (i, j, k) in x])
            solver.Add(y[i, j] <= used)
            solver.Add(y[i, j] * max_cuts_per_roll >= used)
    
    # 各ロールで使用される幅の種類数
    width_types_per_roll = []
    for j in range(num_rolls):
        width_types_per_roll.append(solver.Sum([y[i, j] for i in range(num_demands)]))
    
    # ターゲットロールのインデックスを特定
    target_j = -1
    for j in range(num_rolls):
        if optimization_rolls[j]["is_target"]:
            target_j = j
            break
    
    if target_j == -1:
        return results
    
    # ターゲットロールの使用幅を計算
    target_used_width = solver.Sum([
        x[i, target_j, k] * k * (demands[i]["width"] + blade_width)
        for i in range(num_demands)
        for k in range(1, max_cuts_per_roll + 1)
        if (i, target_j, k) in x
    ])
    
    # ターゲットロールの残り幅
    target_remain = optimization_rolls[target_j]["width"] - edge_loss - target_used_width + blade_width
    
    # 他のロールの残り幅の合計
    other_remains = []
    for j in range(num_rolls):
        if j != target_j:
            used_width_j = solver.Sum([
                x[i, j, k] * k * (demands[i]["width"] + blade_width)
                for i in range(num_demands)
                for k in range(1, max_cuts_per_roll + 1)
                if (i, j, k) in x
            ])
            remain_j = optimization_rolls[j]["width"] - edge_loss - used_width_j + blade_width
            other_remains.append(remain_j)
    
    # 幅の種類数ペナルティ（ターゲットロールは除外）
    width_variety_penalty = solver.Sum([width_types_per_roll[j] for j in range(num_rolls) if j != target_j])
    
    # 目的関数：ターゲットロールの残り幅最大化 + 他のロールの残り幅最小化 + 同一幅カットボーナス
    if other_remains:
        solver.Maximize(target_remain * 1000 - solver.Sum(other_remains) * 100 - width_variety_penalty * 10)
    else:
        solver.Maximize(target_remain * 1000 - width_variety_penalty * 10)
    
    solver.SetTimeLimit(30000)  # 30秒
    status = solver.Solve()
    
    if status != pywraplp.Solver.OPTIMAL and status != pywraplp.Solver.FEASIBLE:
        return results
    
    # 結果を反映（元の順序を保持）
    new_results = []
    for orig_r in results:
        new_results.append({
            "width": orig_r["width"],
            "length": orig_r["length"],
            "cuts": 0,
            "layout": [],
            "remain": orig_r["width"] - edge_loss
        })
    
    # 最適化されたロールの結果を反映
    for j in range(num_rolls):
        original_idx = optimization_rolls[j]["original_idx"]
        layout = []
        
        for i in range(num_demands):
            for k in range(1, max_cuts_per_roll + 1):
                if (i, j, k) in x and x[i, j, k].solution_value() > 0.5:
                    for _ in range(k):
                        layout.append(demands[i]["width"])
        
        if layout:
            # 同じ幅でグループ化してソート
            layout.sort()
            used = sum(layout) + blade_width * (len(layout) - 1)
            remain = optimization_rolls[j]["width"] - edge_loss - used
            new_results[original_idx] = {
                "width": optimization_rolls[j]["width"],
                "length": optimization_rolls[j]["length"],
                "cuts": len(layout),
                "layout": layout,
                "remain": remain
            }
    
    return new_results

if st.button(T["exec"]):
    base_result = assign_rolls(copy.deepcopy(demands), copy.deepcopy(stock), edge_loss, blade_width)
    optimized_result = optimize_last_roll(base_result, edge_loss, blade_width, demands) if use_advanced else base_result
    
    # 高度な最適化を使用した場合、ターゲットロール（最も幅が広く巻長が長い）を最後に配置
    if use_advanced and len(optimized_result) > 1:
        # ターゲットロールを特定
        target_index = -1
        max_score = -1
        for idx, r in enumerate(optimized_result):
            score = r["width"] * 1000 + r["length"]
            if score > max_score:
                max_score = score
                target_index = idx
        
        # ターゲットロールを最後に移動
        if target_index != -1 and target_index != len(optimized_result) - 1:
            result = []
            for idx, r in enumerate(optimized_result):
                if idx != target_index:
                    result.append(r)
            result.append(optimized_result[target_index])
        else:
            result = optimized_result
    else:
        result = optimized_result

    st.header(T["result"])
    df = pd.DataFrame(result)
    df.index += 1
    df.index.name = "ロール#" if lang == "日本語" else "Cuộn#"

    feedback_col = []
    usage_col = []
    remaining_col = []
    for r in result:
        # 使用量の計算 - パラメーター入力の材料幅を使用
        total_cut_width = sum(r["layout"])
        if material_width > 0:
            usage = (total_cut_width / material_width) * r["length"]
            usage_col.append(f"{usage:.1f}")
            # 残量の計算
            remaining = (r["width"] / material_width) * r["length"] - usage
            remaining_col.append(f"{remaining:.1f}")
        else:
            usage_col.append("0.0")
            remaining_col.append("0.0")
        
        # フィードバックの生成
        if r["remain"] > 0:
            msg_ja = f"{int(r['remain'])}mmの端材。{int(r['remain'])}mm以下の幅で{int(r['length'])}Mの追加WO検討"
            msg_vi = f"Có {int(r['remain'])}mm vật liệu thừa. Xem xét phát hành WO bổ sung dưới {int(r['remain'])}mm, dài {int(r['length'])}M"
            feedback_col.append(msg_ja if lang == "日本語" else msg_vi)
        else:
            feedback_col.append("")
    
    df["使用量" if lang == "日本語" else "Sản lượng"] = usage_col
    df["残量" if lang == "日本語" else "Còn lại"] = remaining_col
    df[FEEDBACK_HEADER[lang]] = feedback_col
    df.columns = TABLE_HEADERS[lang]

    st.dataframe(df, use_container_width=True)
    st.download_button(label=T["download"], data=df.to_csv(index=False, encoding="utf-8-sig"), file_name="cutting_result.csv", mime="text/csv")