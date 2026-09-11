const state = { files: [], token: null, datasets: [], report: null };

const $ = (id) => document.getElementById(id);
const elements = {
  fileInput: $("fileInput"), dropzone: $("dropzone"), fileList: $("fileList"),
  inspectButton: $("inspectButton"), uploadMessage: $("uploadMessage"), mappingStep: $("mappingStep"),
  campaignDataset: $("campaignDataset"), productDataset: $("productDataset"),
  campaignFields: $("campaignFields"), productFields: $("productFields"),
  generateButton: $("generateButton"), mappingMessage: $("mappingMessage"),
  reportShell: $("reportShell"), toast: $("toast"), printTopButton: $("printTopButton"),
};

const campaignFieldSpec = [
  ["campaign", "캠페인명", true], ["spend", "광고비", true], ["sales", "매출", true],
  ["clicks", "클릭수", false], ["orders", "주문수 / 전환수", false], ["conversion_rate", "전환율", false],
];
const productFieldSpec = [
  ["option_id", "옵션 ID", false], ["product_name", "상품명", true],
  ["sales", "매출액", true], ["quantity", "판매 수량", false],
];

const won = new Intl.NumberFormat("ko-KR", { maximumFractionDigits: 0 });
const number = new Intl.NumberFormat("ko-KR", { maximumFractionDigits: 0 });
const percent = (value) => value == null || !Number.isFinite(value) ? "-" : `${value.toFixed(1)}%`;
const money = (value) => `${won.format(Math.round(value || 0))}원`;
const compactMoney = (value) => `${won.format(Math.round(value || 0))}`;

function showToast(message) {
  elements.toast.textContent = message;
  elements.toast.classList.add("is-visible");
  window.clearTimeout(showToast.timer);
  showToast.timer = window.setTimeout(() => elements.toast.classList.remove("is-visible"), 2600);
}

function setMessage(element, message = "", error = false) {
  element.textContent = message;
  element.classList.toggle("is-error", error);
}

function setFiles(fileList) {
  state.files = [...fileList];
  elements.inspectButton.disabled = state.files.length === 0;
  elements.fileList.innerHTML = state.files.map((file) => `
    <div class="file-item"><span>${escapeHtml(file.name)}</span><small>${formatBytes(file.size)}</small></div>
  `).join("");
  setMessage(elements.uploadMessage, state.files.length ? `${state.files.length}개 파일이 선택되었습니다.` : "");
}

function formatBytes(bytes) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 ** 2) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 ** 2).toFixed(1)} MB`;
}

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>'"]/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;" }[char]));
}

function currentDataset(selectElement) {
  return state.datasets.find((dataset) => dataset.id === selectElement.value);
}

function scoreDataset(dataset, fields) {
  return fields.reduce((score, [key, , required]) => score + (dataset.detected[key] ? (required ? 4 : 1) : 0), 0);
}

function fillDatasetSelect(select, selectedId) {
  select.innerHTML = state.datasets.map((dataset) => `<option value="${escapeHtml(dataset.id)}">${escapeHtml(dataset.label)} (${number.format(dataset.rowCount)}행)</option>`).join("");
  select.value = selectedId;
}

function bestDataset(fields) {
  return [...state.datasets].sort((a, b) => scoreDataset(b, fields) - scoreDataset(a, fields))[0]?.id;
}

function renderFields(container, dataset, specs, prefix) {
  if (!dataset) { container.innerHTML = ""; return; }
  const options = [`<option value="">사용하지 않음</option>`, ...dataset.columns.map((column) => `<option value="${escapeHtml(column)}">${escapeHtml(column)}</option>`)].join("");
  container.innerHTML = specs.map(([key, label, required]) => `
    <label><span>${escapeHtml(label)}${required ? " *" : ""}</span><select id="${prefix}-${key}" data-field="${key}">${options}</select></label>
  `).join("");
  specs.forEach(([key]) => {
    const select = $(`${prefix}-${key}`);
    if (dataset.detected[key]) select.value = dataset.detected[key];
  });
}

function refreshCampaignFields() {
  renderFields(elements.campaignFields, currentDataset(elements.campaignDataset), campaignFieldSpec, "campaign");
}
function refreshProductFields() {
  renderFields(elements.productFields, currentDataset(elements.productDataset), productFieldSpec, "product");
}

async function inspectFiles() {
  if (!state.files.length) return;
  elements.inspectButton.disabled = true;
  elements.inspectButton.textContent = "파일 읽는 중…";
  setMessage(elements.uploadMessage, "시트와 열 이름을 확인하고 있습니다.");
  const formData = new FormData();
  state.files.forEach((file) => formData.append("files", file));
  try {
    const response = await fetch("/api/inspect", { method: "POST", body: formData });
    const result = await response.json();
    if (!response.ok || !result.ok) throw new Error(result.error || "파일을 읽지 못했습니다.");
    state.token = result.token;
    state.datasets = result.datasets;
    const campaignId = bestDataset(campaignFieldSpec);
    const productId = bestDataset(productFieldSpec);
    fillDatasetSelect(elements.campaignDataset, campaignId);
    fillDatasetSelect(elements.productDataset, productId);
    refreshCampaignFields();
    refreshProductFields();
    elements.mappingStep.classList.add("is-active");
    setMessage(elements.uploadMessage, `${state.datasets.length}개 데이터 시트를 찾았습니다.${result.warnings.length ? ` ${result.warnings.join(" ")}` : ""}`);
    elements.mappingStep.scrollIntoView({ behavior: "smooth", block: "start" });
  } catch (error) {
    setMessage(elements.uploadMessage, error.message, true);
  } finally {
    elements.inspectButton.disabled = false;
    elements.inspectButton.textContent = "열 구성 다시 확인";
  }
}

function collectMapping(prefix, specs) {
  return Object.fromEntries(specs.map(([key]) => [key, $(`${prefix}-${key}`)?.value || null]));
}

function missingRequired(mapping, specs) {
  return specs.filter(([, , required]) => required).filter(([key]) => !mapping[key]).map(([, label]) => label);
}

async function generateReport() {
  const campaignMapping = collectMapping("campaign", campaignFieldSpec);
  const productMapping = collectMapping("product", productFieldSpec);
  const missing = [...missingRequired(campaignMapping, campaignFieldSpec), ...missingRequired(productMapping, productFieldSpec)];
  if (missing.length) {
    setMessage(elements.mappingMessage, `필수 열을 선택해주세요: ${[...new Set(missing)].join(", ")}`, true);
    return;
  }
  elements.generateButton.disabled = true;
  elements.generateButton.textContent = "집계하는 중…";
  setMessage(elements.mappingMessage, "캠페인과 상품별 데이터를 집계하고 있습니다.");
  try {
    const response = await fetch("/api/generate", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        token: state.token,
        campaignDatasetId: elements.campaignDataset.value,
        productDatasetId: elements.productDataset.value,
        campaignMapping, productMapping,
        meta: { periodType: $("periodType").value, periodLabel: $("periodLabel").value, reportTitle: $("reportTitle").value },
      }),
    });
    const result = await response.json();
    if (!response.ok || !result.ok) throw new Error(result.error || "보고서를 생성하지 못했습니다.");
    renderReport(result.report);
    setMessage(elements.mappingMessage, "집계가 완료되었습니다.");
  } catch (error) {
    setMessage(elements.mappingMessage, error.message, true);
  } finally {
    elements.generateButton.disabled = false;
    elements.generateButton.textContent = "보고서 다시 생성";
  }
}

function renderReport(report) {
  state.report = report;
  const weekly = report.meta.periodType === "weekly";
  $("reportKicker").textContent = weekly ? "WEEKLY AD PERFORMANCE" : "MONTHLY AD PERFORMANCE";
  $("outputTitle").textContent = report.meta.reportTitle;
  $("outputPeriod").textContent = report.meta.periodLabel;
  $("totalSpend").textContent = money(report.kpis.totalSpend);
  $("totalSales").textContent = money(report.kpis.totalSales);
  $("conversionRate").textContent = percent(report.kpis.conversionRate);
  $("roas").textContent = percent(report.kpis.roas);
  $("spendToSales").textContent = percent(report.kpis.spendToSales);

  $("campaignTable").innerHTML = report.campaigns.length ? report.campaigns.map((row) => `
    <tr>
      <td class="name">${escapeHtml(row.campaign)}</td>
      <td class="number">${compactMoney(row.spend)}</td>
      <td class="number">${compactMoney(row.sales)}</td>
      <td class="number">${percent(row.conversionRate)}</td>
      <td class="number"><span class="campaign-share"><span class="share-bar"><i style="width:${Math.min(100, Math.max(0, row.spendShare))}%"></i></span>${percent(row.spendShare)}</span></td>
    </tr>`).join("") : `<tr class="empty-row"><td colspan="5">표시할 캠페인 데이터가 없습니다.</td></tr>`;

  $("productTable").innerHTML = report.products.length ? report.products.map((row, index) => `
    <tr>
      <td class="rank">${String(index + 1).padStart(2, "0")}</td>
      <td>${escapeHtml(row.optionId)}</td>
      <td class="name">${escapeHtml(row.productName)}</td>
      <td class="number">${compactMoney(row.sales)}</td>
      <td class="number">${number.format(row.quantity)}</td>
    </tr>`).join("") : `<tr class="empty-row"><td colspan="5">표시할 상품 데이터가 없습니다.</td></tr>`;

  $("qualityNote").textContent = `캠페인 ${number.format(report.quality.campaignRows)}행 · 상품 ${number.format(report.quality.productRows)}행 · 전환율: ${report.quality.conversionMethod}`;
  $("sourceNote").textContent = `SOURCE · ${report.meta.sourceNames.join(", ")}`;
  $("generatedAt").textContent = `GENERATED · ${new Intl.DateTimeFormat("ko-KR", { dateStyle: "medium", timeStyle: "short" }).format(new Date())}`;
  elements.reportShell.hidden = false;
  elements.printTopButton.disabled = false;
  window.setTimeout(() => elements.reportShell.scrollIntoView({ behavior: "smooth", block: "start" }), 80);
}

const sampleReport = {
  meta: { periodType: "monthly", periodLabel: "2026년 8월", reportTitle: "광고 성과 리포트", sourceNames: ["샘플 광고 데이터.xlsx"] },
  kpis: { totalSpend: 34838655, totalSales: 244437066, conversionRate: 9.0, roas: 701.6, spendToSales: 14.3 },
  campaigns: [
    { campaign: "브랜드 검색광고", spend: 11520400, sales: 94632400, conversionRate: 10.4, spendShare: 33.1 },
    { campaign: "주력상품 자동광고", spend: 9868255, sales: 72140760, conversionRate: 8.9, spendShare: 28.3 },
    { campaign: "신제품 런칭", spend: 7420000, sales: 44901020, conversionRate: 6.8, spendShare: 21.3 },
    { campaign: "리타겟팅", spend: 6030000, sales: 32762886, conversionRate: 9.6, spendShare: 17.3 },
  ],
  products: [
    { optionId: "86412001", productName: "LED 아토실링팬 방등 50W", sales: 24890500, quantity: 142 },
    { optionId: "86412018", productName: "LED 에코 슬림직하엣지 1285×320", sales: 21742090, quantity: 429 },
    { optionId: "86412027", productName: "클래식 1로 2구 스위치 16A", sales: 18674130, quantity: 1369 },
    { optionId: "86412035", productName: "LED 십자등 60W 주광색", sales: 16072530, quantity: 868 },
    { optionId: "86412044", productName: "클래식 매입접지 2구 콘센트", sales: 14064169, quantity: 1590 },
    { optionId: "86412052", productName: "LED 노출투광등 200W 흑색", sales: 12003110, quantity: 141 },
    { optionId: "86412061", productName: "고효율 LED 다운라이트 6인치", sales: 10742500, quantity: 624 },
    { optionId: "86412079", productName: "방수형 3구 멀티탭 5M", sales: 9670060, quantity: 302 },
    { optionId: "86412087", productName: "스마트 플러그 16A", sales: 8643830, quantity: 287 },
    { optionId: "86412096", productName: "LED 센서등 원형 20W", sales: 8003110, quantity: 354 },
  ],
  quality: { campaignRows: 4, productRows: 10, conversionMethod: "주문수 ÷ 클릭수" },
};

elements.fileInput.addEventListener("change", (event) => setFiles(event.target.files));
["dragenter", "dragover"].forEach((name) => elements.dropzone.addEventListener(name, (event) => { event.preventDefault(); elements.dropzone.classList.add("is-dragging"); }));
["dragleave", "drop"].forEach((name) => elements.dropzone.addEventListener(name, (event) => { event.preventDefault(); elements.dropzone.classList.remove("is-dragging"); }));
elements.dropzone.addEventListener("drop", (event) => setFiles(event.dataTransfer.files));
elements.inspectButton.addEventListener("click", inspectFiles);
elements.campaignDataset.addEventListener("change", refreshCampaignFields);
elements.productDataset.addEventListener("change", refreshProductFields);
elements.generateButton.addEventListener("click", generateReport);
$("sampleButton").addEventListener("click", () => { renderReport(sampleReport); showToast("샘플 보고서를 불러왔습니다."); });
[$("printButton"), elements.printTopButton].forEach((button) => button.addEventListener("click", () => window.print()));
