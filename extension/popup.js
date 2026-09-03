// ============================================================
// Company Research Chrome Extension 前端逻辑
//
// 功能：
// 1. 获取用户输入的公司名称
// 2. 点击按钮或按 Enter 后向本地 FastAPI 发送请求
// 3. 接收公司背调结果
// 4. 显示 Company Identity、Employer Verification 和 Sources
// ============================================================


const button = document.getElementById("researchButton");
const companyInput = document.getElementById("companyInput");
const resultDiv = document.getElementById("result");
const loadingDiv = document.getElementById("loading");


// ------------------------------------------------------------
// 公司背调主函数
// ------------------------------------------------------------

async function researchCompany() {

    const company = companyInput.value.trim();

    if (!company) {
        resultDiv.innerHTML = "Please enter a company name.";
        return;
    }


    // 显示 loading
    loadingDiv.style.display = "block";
    resultDiv.innerHTML = "";


    try {

        // ----------------------------------------------------
        // 调用本地 FastAPI
        // ----------------------------------------------------

        const response = await fetch(
            `http://127.0.0.1:8000/research?company=${encodeURIComponent(company)}`
        );


        if (!response.ok) {
            throw new Error("Research request failed");
        }


        const data = await response.json();

        const report = data.report;


        // ----------------------------------------------------
        // 显示公司背调结果
        // ----------------------------------------------------

        resultDiv.innerHTML = `
            <h2>${report.company}</h2>

            <div class="section">

                <p>
                    <strong>Type</strong><br>
                    ${report.company_type}
                </p>

                <p>
                    <strong>Employer Type</strong><br>
                    ${report.employer_type}
                </p>

                <p>
                    <strong>Direct Employer</strong><br>
                    ${report.direct_employer}
                </p>

                <p>
                    <strong>Industry</strong><br>
                    ${report.industry}
                </p>

                <p>
                    <strong>Company Size</strong><br>
                    ${report.company_size}
                </p>

                <p>
                    <strong>Headquarters</strong><br>
                    ${report.headquarters}
                </p>

                <p>
                    <strong>Primary Base</strong><br>
                    ${report.primary_base}
                </p>

                <p>
                    <strong>Legitimacy</strong><br>
                    ${report.legitimacy_signal}
                </p>

                <p>
                    <strong>Confidence</strong><br>
                    ${report.verification_confidence}
                </p>

                <p>
                    <strong>⚠ Note</strong><br>
                    ${report.warning}
                </p>

                <p>
                    <strong>Official Website</strong><br>
                    ${
                        report.official_website &&
                        report.official_website !== "Not clearly found"
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

            <div class="section">

                <h3>Sources</h3>

                ${data.sources
                    .map(source => `
                        <p>
                            <a
                                href="${source.url}"
                                target="_blank"
                            >
                                ${source.title}
                            </a>
                        </p>
                    `)
                    .join("")}

            </div>
        `;


    } catch (error) {

        resultDiv.innerHTML = `
            <p>
                Could not research this company.
            </p>
        `;

        console.error(error);

    } finally {

        // 无论成功还是失败都关闭 loading
        loadingDiv.style.display = "none";

    }
}


// ------------------------------------------------------------
// 点击 Research Company 按钮
// ------------------------------------------------------------

button.addEventListener(
    "click",
    researchCompany
);


// ------------------------------------------------------------
// 输入公司名称后按 Enter 也可以直接搜索
// ------------------------------------------------------------

companyInput.addEventListener(
    "keydown",
    function(event) {

        if (event.key === "Enter") {
            researchCompany();
        }

    }
);