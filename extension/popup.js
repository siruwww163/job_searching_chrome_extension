// ============================================================
// Company Research Chrome Extension 前端逻辑
//
// 功能：
// 1. 输入公司名称后调用 FastAPI
// 2. Backend 有缓存时直接显示 SQLite 中的旧结果
// 3. 显示结果是否来自 Cache
// 4. 显示上次搜索时间
// 5. 提供 Refresh Research 强制重新调用 Tavily + Claude
// 6. 防止缺失字段显示 undefined
// ============================================================


const button = document.getElementById("researchButton");
const companyInput = document.getElementById("companyInput");
const resultDiv = document.getElementById("result");
const loadingDiv = document.getElementById("loading");


// ------------------------------------------------------------
// 防止 undefined
// ------------------------------------------------------------

function displayValue(
    value,
    fallback = "Not clearly found"
) {

    if (
        value === undefined ||
        value === null ||
        value === ""
    ) {
        return fallback;
    }

    return value;
}


// ------------------------------------------------------------
// 格式化搜索时间
// ------------------------------------------------------------

function formatSearchedTime(dateString) {

    if (!dateString) {
        return "Unknown";
    }

    const date = new Date(dateString);

    return date.toLocaleString();
}


// ------------------------------------------------------------
// 将 Backend 返回的数据画到 Popup
// ------------------------------------------------------------

function renderResult(data) {

    const report = data.report;

    const cacheLabel = data.from_cache
        ? "Cached Result"
        : "Fresh Research";


    resultDiv.innerHTML = `

        <h2>
            ${displayValue(report.company)}
        </h2>


        <p>
            <strong>${cacheLabel}</strong><br>
            Last researched:
            ${formatSearchedTime(data.searched_at)}
        </p>


        <div class="section">

            <p>
                <strong>Type</strong><br>
                ${displayValue(report.company_type)}
            </p>


            <p>
                <strong>Employer Type</strong><br>
                ${displayValue(
                    report.employer_type,
                    "Unknown"
                )}
            </p>


            <p>
                <strong>Direct Employer</strong><br>
                ${displayValue(
                    report.direct_employer,
                    "Unclear"
                )}
            </p>


            <p>
                <strong>Industry</strong><br>
                ${displayValue(report.industry)}
            </p>


            <p>
                <strong>Company Size</strong><br>
                ${displayValue(report.company_size)}
            </p>


            <p>
                <strong>Headquarters</strong><br>
                ${displayValue(report.headquarters)}
            </p>


            <p>
                <strong>Primary Base</strong><br>
                ${displayValue(report.primary_base)}
            </p>


            <p>
                <strong>Legitimacy</strong><br>
                ${displayValue(
                    report.legitimacy_signal,
                    "Insufficient Information"
                )}
            </p>


            <p>
                <strong>Confidence</strong><br>
                ${displayValue(
                    report.verification_confidence,
                    "Low"
                )}
            </p>


            <p>
                <strong>⚠ Note</strong><br>
                ${displayValue(
                    report.warning,
                    "No major concern found."
                )}
            </p>


            <p>
                <strong>Official Website</strong><br>

                ${
                    report.official_website &&
                    report.official_website !==
                        "Not clearly found"

                        ? `
                            <a
                                href="${report.official_website}"
                                target="_blank"
                            >
                                ${report.official_website}
                            </a>
                          `

                        : "Not clearly found"
                }

            </p>

        </div>


        <button id="refreshResearchButton">
            Refresh Research
        </button>


        <div class="section">

            <h3>Sources</h3>

            ${
                data.sources &&
                data.sources.length > 0

                    ? data.sources
                        .slice(0, 5)
                        .map(
                            source => `
                                <p>
                                    <a
                                        href="${source.url}"
                                        target="_blank"
                                    >
                                        ${displayValue(
                                            source.title,
                                            source.url
                                        )}
                                    </a>
                                </p>
                            `
                        )
                        .join("")

                    : "<p>No sources found.</p>"
            }

        </div>
    `;


    // --------------------------------------------------------
    // Refresh 按钮
    // --------------------------------------------------------

    const refreshButton =
        document.getElementById(
            "refreshResearchButton"
        );

    refreshButton.addEventListener(
        "click",
        function() {

            researchCompany(true);

        }
    );
}


// ------------------------------------------------------------
// 公司背调
//
// forceRefresh = false
// → Backend 可以使用 Cache
//
// forceRefresh = true
// → Backend 强制重新搜索
// ------------------------------------------------------------

async function researchCompany(
    forceRefresh = false
) {

    const company =
        companyInput.value.trim();

    if (!company) {

        resultDiv.innerHTML =
            "Please enter a company name.";

        return;
    }


    loadingDiv.style.display = "block";


    // Refresh 时保留旧结果，
    // 避免重新搜索期间整个 Popup 变空
    if (!forceRefresh) {
        resultDiv.innerHTML = "";
    }


    try {

        const refreshParameter =
            forceRefresh
                ? "&refresh=true"
                : "";


        const response = await fetch(
            `http://127.0.0.1:8000/research?company=${
                encodeURIComponent(company)
            }${refreshParameter}`
        );


        if (!response.ok) {

            throw new Error(
                "Research request failed"
            );

        }


        const data =
            await response.json();


        renderResult(data);


    } catch (error) {

        if (!forceRefresh) {

            resultDiv.innerHTML = `
                <p>
                    Could not research this company.
                </p>
            `;

        }

        console.error(error);


    } finally {

        loadingDiv.style.display = "none";

    }
}


// ------------------------------------------------------------
// Research Company
// ------------------------------------------------------------

button.addEventListener(
    "click",
    function() {

        researchCompany(false);

    }
);


// ------------------------------------------------------------
// Enter
// ------------------------------------------------------------

companyInput.addEventListener(
    "keydown",
    function(event) {

        if (event.key === "Enter") {

            researchCompany(false);

        }

    }
);