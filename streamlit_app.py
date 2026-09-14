from __future__ import annotations

import hashlib
import html
from datetime import datetime
from pathlib import Path
from typing import Any

import streamlit as st

from report_engine import Dataset, build_report, find_column, read_upload


BASE_DIR = Path(__file__).resolve().parent
CAMPAIGN_FIELDS = [
    ("campaign", "캠페인명", True),
    ("spend", "광고비", True),
    ("clicks", "클릭수", True),
]
PRODUCT_FIELDS = [
    ("option_id", "옵션 ID", False),
    ("product_name", "상품명", True),
]
CAMPAIGN_SCORE_FIELDS = [
    *CAMPAIGN_FIELDS,
    ("sales", "매출", True),
    ("orders", "주문수 / 전환수", True),
]
PRODUCT_SCORE_FIELDS = [
    *PRODUCT_FIELDS,
    ("sales", "매출액", True),
    ("quantity", "판매 수량", True),
]

ORDERS_14D_ALIASES = ["총 주문수(14일)", "총주문수(14일)", "총 주문수 14일"]
SALES_14D_ALIASES = [
    "총 전환 매출액(14일)",
    "총 전환 매출액(14일)(원)",
    "총 전환 매출(14일)",
]
QUANTITY_14D_ALIASES = ["총 판매 수량(14일)", "총판매수량(14일)", "총 판매수량 14일"]


st.set_page_config(
    page_title="광고 리포트 자동화",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="collapsed",
)


st.markdown(
    """
<style>
  :root { --ink:#101827; --muted:#667085; --line:#e3e8ef; --accent:#2463eb; --surface:#f5f7fa; }
  .stApp { background: var(--surface); color: var(--ink); }
  [data-testid="stHeader"] { background: rgba(245,247,250,.88); }
  [data-testid="stMainBlockContainer"] { max-width: 1180px; padding-top: 2.2rem; padding-bottom: 5rem; }
  #MainMenu, footer { visibility: hidden; }
  .app-brand { display:flex; align-items:center; gap:12px; margin-bottom:3.2rem; }
  .app-mark { width:42px; height:42px; display:grid; place-items:center; border-radius:11px; background:var(--ink); color:white; font-weight:800; letter-spacing:-.04em; }
  .app-brand strong { display:block; font-size:13px; letter-spacing:.14em; }
  .app-brand small { display:block; margin-top:2px; color:var(--muted); font-size:11px; }
  .hero-kicker { color:var(--accent); font-size:12px; font-weight:800; letter-spacing:.14em; margin-bottom:14px; }
  .hero-title { max-width:720px; margin:0; font-size:clamp(38px,5vw,64px); line-height:1.04; letter-spacing:-.055em; }
  .hero-copy { max-width:600px; margin:18px 0 36px; color:var(--muted); font-size:16px; line-height:1.7; }
  .section-label { margin:1.6rem 0 .7rem; color:var(--ink); font-size:17px; font-weight:800; letter-spacing:-.02em; }
  .privacy-note { padding:12px 14px; border:1px solid #d8e3fa; border-radius:10px; background:#eef4ff; color:#344054; font-size:12px; line-height:1.55; }
  [data-testid="stFileUploaderDropzone"] { min-height:150px; border:1.5px dashed #b9c4d4; border-radius:14px; background:white; }
  [data-testid="stFileUploaderDropzone"] button { border-radius:9px; }
  [data-testid="stVerticalBlockBorderWrapper"] { background:white; border-color:var(--line); border-radius:14px; box-shadow:0 12px 32px rgba(25,37,56,.04); }
  .stButton > button, .stDownloadButton > button { min-height:45px; border-radius:10px; font-weight:700; }
  .stButton > button[kind="primary"] { background:var(--accent); border-color:var(--accent); }
  .stSelectbox label, .stTextInput label, .stRadio label { font-size:12px; font-weight:700; color:#344054; }
  .mapping-help { margin:-4px 0 12px; color:var(--muted); font-size:12px; }
  .success-title { margin:3rem 0 .8rem; font-size:24px; font-weight:800; letter-spacing:-.035em; }
  @media (max-width:700px) {
    [data-testid="stMainBlockContainer"] { padding-left:1rem; padding-right:1rem; }
    .app-brand { margin-bottom:2rem; }
  }
</style>
""",
    unsafe_allow_html=True,
)


def esc(value: Any) -> str:
    return html.escape(str(value if value is not None else ""))


def money(value: Any) -> str:
    return f"{round(float(value or 0)):,}원"


def number(value: Any) -> str:
    return f"{round(float(value or 0)):,}"


def percent(value: Any) -> str:
    return "-" if value is None else f"{float(value):.1f}%"


def parse_files(file_payloads: tuple[tuple[str, bytes], ...]) -> tuple[list[Dataset], list[str]]:
    datasets: list[Dataset] = []
    warnings: list[str] = []
    for file_index, (file_name, data) in enumerate(file_payloads):
        try:
            datasets.extend(read_upload(data, file_name, f"f{file_index}"))
        except ValueError as exc:
            warnings.append(f"{file_name}: {exc}")
    return datasets, warnings


def file_signature(file_payloads: tuple[tuple[str, bytes], ...]) -> str:
    digest = hashlib.sha256()
    for file_name, data in file_payloads:
        digest.update(file_name.encode("utf-8"))
        digest.update(data)
    return digest.hexdigest()


def score_dataset(dataset: Dataset, fields: list[tuple[str, str, bool]]) -> int:
    detected = dataset.public_summary()["detected"]
    return sum((4 if required else 1) for key, _, required in fields if detected.get(key))


def best_dataset_id(datasets: list[Dataset], fields: list[tuple[str, str, bool]]) -> str:
    return max(datasets, key=lambda item: score_dataset(item, fields)).dataset_id


def dataset_label(dataset: Dataset) -> str:
    return f"{dataset.file_name} · {dataset.sheet_name} ({len(dataset.rows):,}행)"


def mapping_widgets(
    dataset: Dataset,
    fields: list[tuple[str, str, bool]],
    prefix: str,
) -> dict[str, str | None]:
    detected = dataset.public_summary()["detected"]
    mapping: dict[str, str | None] = {}
    columns = st.columns(2)
    for index, (field, label, required) in enumerate(fields):
        options: list[str | None] = [None, *dataset.columns]
        default = detected.get(field)
        default_index = options.index(default) if default in options else 0
        with columns[index % 2]:
            mapping[field] = st.selectbox(
                f"{label}{' *' if required else ''}",
                options,
                index=default_index,
                format_func=lambda value: "사용하지 않음" if value is None else value,
                key=f"{prefix}:{dataset.dataset_id}:{field}",
            )
    return mapping


def render_report_html(report: dict[str, Any], standalone: bool = False) -> str:
    campaign_rows = "".join(
        f"""
        <tr>
          <td class="name">{esc(row['campaign'])}</td>
          <td class="num">{number(row['spend'])}</td>
          <td class="num">{number(row['sales'])}</td>
          <td class="num">{percent(row['conversionRate'])}</td>
          <td class="num"><span class="share"><i><b style="width:{min(100,max(0,row['spendShare'])):.1f}%"></b></i>{percent(row['spendShare'])}</span></td>
        </tr>
        """
        for row in report["campaigns"]
    ) or '<tr><td colspan="5" class="empty">표시할 캠페인 데이터가 없습니다.</td></tr>'

    product_rows = "".join(
        f"""
        <tr>
          <td class="rank">{index:02d}</td>
          <td>{esc(row['optionId'])}</td>
          <td class="name">{esc(row['productName'])}</td>
          <td class="num">{number(row['sales'])}</td>
          <td class="num">{number(row['quantity'])}</td>
        </tr>
        """
        for index, row in enumerate(report["products"], 1)
    ) or '<tr><td colspan="5" class="empty">표시할 상품 데이터가 없습니다.</td></tr>'

    generated = datetime.now().strftime("%Y.%m.%d %H:%M")
    source_names = ", ".join(report["meta"]["sourceNames"])
    kicker = "WEEKLY AD PERFORMANCE" if report["meta"]["periodType"] == "weekly" else "MONTHLY AD PERFORMANCE"
    print_button = '<button class="print-button" onclick="window.print()">PDF로 저장 / 인쇄</button>'

    document = f"""
<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(report['meta']['reportTitle'])}</title>
<style>
  * {{ box-sizing:border-box; }}
  body {{ margin:0; padding:18px; background:#f3f5f8; color:#101827; font-family:"Pretendard","Noto Sans KR","Malgun Gothic",Arial,sans-serif; }}
  .actions {{ max-width:1120px; margin:0 auto 10px; display:flex; justify-content:flex-end; }}
  .print-button {{ min-height:42px; padding:0 18px; border:0; border-radius:10px; background:#101827; color:white; font:700 13px inherit; cursor:pointer; }}
  .report {{ max-width:1120px; margin:auto; padding:48px 50px 24px; background:white; border:1px solid #e3e8ef; box-shadow:0 18px 50px rgba(25,37,56,.08); }}
  .head {{ display:flex; justify-content:space-between; align-items:flex-end; gap:24px; padding-bottom:22px; border-bottom:2px solid #101827; }}
  .kicker {{ margin:0 0 8px; color:#2463eb; font-size:10px; font-weight:800; letter-spacing:.15em; }}
  h1 {{ margin:0; font-size:28px; letter-spacing:-.045em; }}
  .period {{ text-align:right; }} .period span {{ display:block; color:#667085; font-size:8px; font-weight:800; letter-spacing:.13em; }}
  .period strong {{ display:block; margin-top:7px; font-size:13px; }}
  .kpis {{ display:grid; grid-template-columns:repeat(4,1fr); gap:10px; margin-top:22px; }}
  .kpi {{ min-height:118px; display:flex; flex-direction:column; justify-content:space-between; padding:17px; border:1px solid #edf0f4; border-radius:12px; background:#f6f8fb; }}
  .kpi span {{ color:#344054; font-size:11px; font-weight:700; }} .kpi strong {{ margin:13px 0 8px; font-size:24px; letter-spacing:-.045em; white-space:nowrap; }}
  .kpi small {{ color:#98a2b3; font-size:7px; font-weight:800; letter-spacing:.12em; }}
  .kpi.primary {{ color:white; background:#2463eb; border-color:#2463eb; }} .kpi.primary span,.kpi.primary small {{ color:rgba(255,255,255,.78); }}
  .ratio {{ display:grid; grid-template-columns:auto 1fr auto; align-items:baseline; gap:14px; margin-top:10px; padding:13px 16px; border-radius:10px; background:#101827; color:white; }}
  .ratio span {{ font-size:11px; font-weight:700; }} .ratio strong {{ font-size:19px; }} .ratio small {{ color:#aeb7c6; font-size:9px; }}
  section {{ margin-top:38px; }} .section-head {{ display:flex; justify-content:space-between; align-items:end; gap:18px; margin-bottom:11px; }}
  .section-title {{ display:flex; align-items:center; gap:9px; }} .section-title span {{ color:#2463eb; font-size:9px; font-weight:800; }}
  h2 {{ margin:0; font-size:17px; letter-spacing:-.025em; }} .section-head p {{ margin:0; color:#667085; font-size:9px; }}
  .table-wrap {{ overflow-x:auto; }} table {{ width:100%; min-width:670px; border-collapse:collapse; table-layout:fixed; }}
  th {{ padding:10px 11px; border-top:1px solid #101827; border-bottom:1px solid #101827; background:#f7f8fa; color:#344054; text-align:left; font-size:9px; }}
  td {{ padding:10px 11px; border-bottom:1px solid #e3e8ef; color:#344054; font-size:10px; line-height:1.35; }}
  td.name {{ color:#101827; font-weight:700; }} .num {{ text-align:right; }} .rank {{ width:50px; text-align:center; }}
  .share {{ display:inline-flex; align-items:center; justify-content:flex-end; gap:7px; width:100%; }} .share i {{ width:38px; height:4px; background:#e9edf3; border-radius:8px; overflow:hidden; }}
  .share b {{ display:block; height:100%; background:#2463eb; }} .empty {{ padding:24px; text-align:center; color:#667085; }}
  footer {{ display:flex; justify-content:space-between; gap:18px; margin-top:30px; padding-top:12px; border-top:1px solid #e3e8ef; color:#98a2b3; font-size:7px; }}
  @media(max-width:700px) {{ body {{ padding:0; }} .actions {{ padding:10px; margin:0; }} .report {{ padding:28px 15px 18px; border:0; }} .head {{ align-items:flex-start; flex-direction:column; }} .period {{ text-align:left; }} .kpis {{ grid-template-columns:1fr 1fr; }} .ratio {{ grid-template-columns:1fr auto; }} .ratio small {{ grid-column:1/-1; }} }}
  @media(max-width:440px) {{ .kpis {{ grid-template-columns:1fr; }} }}
  @media print {{ @page {{ size:A4; margin:9mm; }} body {{ padding:0; background:white; }} .actions {{ display:none; }} .report {{ max-width:none; padding:0; border:0; box-shadow:none; }} .head {{ padding-bottom:14px; }} .kpis {{ margin-top:14px; gap:7px; }} .kpi {{ min-height:88px; padding:12px; print-color-adjust:exact; -webkit-print-color-adjust:exact; }} .kpi strong {{ margin:8px 0 5px; font-size:18px; }} .ratio {{ margin-top:7px; padding:9px 12px; print-color-adjust:exact; -webkit-print-color-adjust:exact; }} section {{ margin-top:23px; }} th {{ padding:6px 7px; print-color-adjust:exact; -webkit-print-color-adjust:exact; }} td {{ padding:6px 7px; font-size:8px; }} tr {{ break-inside:avoid; }} footer {{ margin-top:16px; }} }}
</style>
</head>
<body>
  <div class="actions">{print_button}</div>
  <article class="report">
    <header class="head">
      <div><p class="kicker">{kicker}</p><h1>{esc(report['meta']['reportTitle'])}</h1></div>
      <div class="period"><span>REPORTING PERIOD</span><strong>{esc(report['meta']['periodLabel'])}</strong></div>
    </header>
    <div class="kpis">
      <div class="kpi"><span>총광고비</span><strong>{money(report['kpis']['totalSpend'])}</strong><small>AD SPEND</small></div>
      <div class="kpi"><span>총매출</span><strong>{money(report['kpis']['totalSales'])}</strong><small>AD SALES</small></div>
      <div class="kpi"><span>전환율</span><strong>{percent(report['kpis']['conversionRate'])}</strong><small>CONVERSION RATE</small></div>
      <div class="kpi primary"><span>ROAS</span><strong>{percent(report['kpis']['roas'])}</strong><small>RETURN ON AD SPEND</small></div>
    </div>
    <div class="ratio"><span>광고 매출 대비 광고비</span><strong>{percent(report['kpis']['spendToSales'])}</strong><small>총광고비 ÷ 총매출</small></div>
    <section>
      <div class="section-head"><div class="section-title"><span>01</span><h2>캠페인별 매출 요약</h2></div><p>매출액 기준 내림차순</p></div>
      <div class="table-wrap"><table><thead><tr><th>캠페인</th><th class="num">광고비</th><th class="num">매출</th><th class="num">전환율</th><th class="num">광고비 비중</th></tr></thead><tbody>{campaign_rows}</tbody></table></div>
    </section>
    <section>
      <div class="section-head"><div class="section-title"><span>02</span><h2>판매상품 TOP 10</h2></div><p>매출액 기준 상위 10개 상품</p></div>
      <div class="table-wrap"><table><thead><tr><th class="rank">순위</th><th>옵션 ID</th><th>상품명</th><th class="num">매출액</th><th class="num">판매 수량</th></tr></thead><tbody>{product_rows}</tbody></table></div>
    </section>
    <footer><span>SOURCE · {esc(source_names)}</span><span>GENERATED · {generated}</span></footer>
  </article>
</body>
</html>
"""
    return document


st.markdown(
    '<div class="app-brand"><span class="app-mark">AR</span><span><strong>AD REPORT</strong><small>광고 리포트 자동화</small></span></div>',
    unsafe_allow_html=True,
)
st.markdown('<div class="hero-kicker">WEEKLY / MONTHLY PERFORMANCE</div>', unsafe_allow_html=True)
st.markdown('<h1 class="hero-title">광고 데이터를<br>읽기 쉬운 보고서로.</h1>', unsafe_allow_html=True)
st.markdown(
    '<p class="hero-copy">엑셀이나 CSV를 올리면 KPI, 캠페인 성과, 판매상품 TOP 10을 자동으로 집계합니다. 열 이름이 달라도 화면에서 바로 연결할 수 있습니다.</p>',
    unsafe_allow_html=True,
)


with st.container(border=True):
    st.markdown('<div class="section-label">01. 데이터 업로드</div>', unsafe_allow_html=True)
    uploaded_files = st.file_uploader(
        "광고 데이터 파일",
        type=["xlsx", "xlsm", "csv", "tsv", "txt"],
        accept_multiple_files=True,
        help="캠페인 데이터와 상품 데이터를 여러 파일 또는 하나의 엑셀 파일 내 여러 시트로 올릴 수 있습니다.",
    )
    st.markdown(
        '<div class="privacy-note">업로드 파일은 Streamlit 서버의 현재 세션 메모리에서 처리되며, 앱은 파일을 별도로 저장하거나 다른 서비스로 재전송하지 않습니다.</div>',
        unsafe_allow_html=True,
    )
    sample_clicked = st.button("샘플 보고서 보기", use_container_width=True)


if sample_clicked:
    sample_payloads = tuple(
        (path.name, path.read_bytes())
        for path in [
            BASE_DIR / "sample_data" / "campaign_sample.csv",
            BASE_DIR / "sample_data" / "product_sample.csv",
        ]
    )
    sample_datasets, _ = parse_files(sample_payloads)
    campaign_sample = max(sample_datasets, key=lambda item: score_dataset(item, CAMPAIGN_SCORE_FIELDS))
    product_sample = max(sample_datasets, key=lambda item: score_dataset(item, PRODUCT_SCORE_FIELDS))
    st.session_state["report"] = build_report(
        campaign_sample,
        product_sample,
        campaign_sample.public_summary()["detected"],
        product_sample.public_summary()["detected"],
        {"periodType": "monthly", "periodLabel": "2026년 8월", "reportTitle": "광고 성과 리포트"},
    )


datasets: list[Dataset] = []
if uploaded_files:
    payloads = tuple((item.name, item.getvalue()) for item in uploaded_files)
    signature = file_signature(payloads)
    if st.session_state.get("upload_signature") != signature:
        parsed, warnings = parse_files(payloads)
        st.session_state["upload_signature"] = signature
        st.session_state["datasets"] = parsed
        st.session_state["warnings"] = warnings
        st.session_state.pop("report", None)
    datasets = st.session_state.get("datasets", [])
    for warning in st.session_state.get("warnings", []):
        st.warning(warning)
    if not datasets:
        st.error("읽을 수 있는 데이터 시트를 찾지 못했습니다.")


if datasets:
    with st.container(border=True):
        st.markdown('<div class="section-label">02. 데이터 연결</div>', unsafe_allow_html=True)
        st.markdown('<div class="mapping-help">자동 선택된 시트와 열을 확인한 뒤 보고서를 생성하세요.</div>', unsafe_allow_html=True)

        meta_columns = st.columns([1, 1.4, 2])
        with meta_columns[0]:
            period_type_label = st.radio("보고서 구분", ["주간", "월간"], horizontal=True, index=1)
        with meta_columns[1]:
            period_label = st.text_input("대상 기간", placeholder="예: 2026년 8월")
        with meta_columns[2]:
            report_title = st.text_input("보고서 제목", value="광고 성과 리포트")

        dataset_by_id = {dataset.dataset_id: dataset for dataset in datasets}
        campaign_default = best_dataset_id(datasets, CAMPAIGN_SCORE_FIELDS)
        campaign_ids = list(dataset_by_id)
        st.markdown('<div class="section-label">캠페인 데이터</div>', unsafe_allow_html=True)
        campaign_id = st.selectbox(
            "캠페인 집계에 사용할 시트",
            campaign_ids,
            index=campaign_ids.index(campaign_default),
            format_func=lambda value: dataset_label(dataset_by_id[value]),
        )
        campaign_mapping = mapping_widgets(dataset_by_id[campaign_id], CAMPAIGN_FIELDS, "campaign")
        campaign_sales_14d_column = find_column(
            dataset_by_id[campaign_id].columns, SALES_14D_ALIASES
        )
        orders_14d_column = find_column(dataset_by_id[campaign_id].columns, ORDERS_14D_ALIASES)
        campaign_mapping["sales"] = campaign_sales_14d_column
        campaign_mapping["orders"] = orders_14d_column
        campaign_mapping["conversion_rate"] = None
        if campaign_sales_14d_column and orders_14d_column:
            st.info(
                f"자동 연결: 매출 → {campaign_sales_14d_column} · 주문수/전환수 → {orders_14d_column} · "
                f"전환율 → {orders_14d_column} ÷ 클릭수 × 100"
            )
        else:
            missing_campaign_auto = []
            if not campaign_sales_14d_column:
                missing_campaign_auto.append("총 전환 매출액(14일)")
            if not orders_14d_column:
                missing_campaign_auto.append("총 주문수(14일)")
            st.error(
                f"자동 연결할 열을 찾지 못했습니다: {', '.join(missing_campaign_auto)}. "
                "원본 파일의 열 이름을 확인해주세요."
            )

        product_default = best_dataset_id(datasets, PRODUCT_SCORE_FIELDS)
        st.markdown('<div class="section-label">상품 데이터</div>', unsafe_allow_html=True)
        product_id = st.selectbox(
            "상품 TOP 10에 사용할 시트",
            campaign_ids,
            index=campaign_ids.index(product_default),
            format_func=lambda value: dataset_label(dataset_by_id[value]),
        )
        product_mapping = mapping_widgets(dataset_by_id[product_id], PRODUCT_FIELDS, "product")
        product_sales_14d_column = find_column(dataset_by_id[product_id].columns, SALES_14D_ALIASES)
        product_quantity_14d_column = find_column(dataset_by_id[product_id].columns, QUANTITY_14D_ALIASES)
        product_mapping["sales"] = product_sales_14d_column
        product_mapping["quantity"] = product_quantity_14d_column
        auto_product_items = [
            f"매출액 → {product_sales_14d_column or '총 전환 매출액(14일) 열 없음'}",
            f"판매 수량 → {product_quantity_14d_column or '총 판매 수량(14일) 열 없음'}",
        ]
        st.info("자동 연결: " + " · ".join(auto_product_items))

        missing_auto_columns = []
        if not campaign_sales_14d_column:
            missing_auto_columns.append("캠페인 총 전환 매출액(14일)")
        if not orders_14d_column:
            missing_auto_columns.append("총 주문수(14일)")
        if not product_sales_14d_column:
            missing_auto_columns.append("상품 총 전환 매출액(14일)")
        if not product_quantity_14d_column:
            missing_auto_columns.append("총 판매 수량(14일)")

        if st.button(
            "보고서 생성",
            type="primary",
            use_container_width=True,
            disabled=bool(missing_auto_columns),
        ):
            missing = [
                label
                for field, label, required in [*CAMPAIGN_FIELDS, *PRODUCT_FIELDS]
                if required
                and not (campaign_mapping.get(field) if (field, label, required) in CAMPAIGN_FIELDS else product_mapping.get(field))
            ]
            if missing:
                st.error(f"필수 열을 선택해주세요: {', '.join(dict.fromkeys(missing))}")
            else:
                try:
                    st.session_state["report"] = build_report(
                        dataset_by_id[campaign_id],
                        dataset_by_id[product_id],
                        campaign_mapping,
                        product_mapping,
                        {
                            "periodType": "weekly" if period_type_label == "주간" else "monthly",
                            "periodLabel": period_label or "기간 미지정",
                            "reportTitle": report_title,
                        },
                    )
                except ValueError as exc:
                    st.error(str(exc))


report = st.session_state.get("report")
if report:
    st.markdown('<div class="success-title">완성된 보고서</div>', unsafe_allow_html=True)
    st.caption(
        f"캠페인 {report['quality']['campaignRows']:,}행 · 상품 {report['quality']['productRows']:,}행 · 전환율: {report['quality']['conversionMethod']}"
    )
    html_report = render_report_html(report)
    download_columns = st.columns([1, 1])
    with download_columns[0]:
        st.download_button(
            "독립 HTML 보고서 내려받기",
            data=html_report.encode("utf-8"),
            file_name="광고_성과_리포트.html",
            mime="text/html",
            use_container_width=True,
        )
    with download_columns[1]:
        st.info("아래 보고서의 ‘PDF로 저장 / 인쇄’를 누르면 PDF로 저장할 수 있습니다.")
    st.iframe(html_report, height="content")
