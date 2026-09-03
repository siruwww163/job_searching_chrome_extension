const button = document.getElementById("researchButton");
const companyInput = document.getElementById("companyInput");
const resultDiv = document.getElementById("result");
const loadingDiv = document.getElementById("loading");


async function researchCompany() {

    const company = companyInput.value.trim();

    if (!company) {
        resultDiv.innerHTML = "Please enter a company name.";
        return;
    }

    loadingDiv.style.display = "block";
    resultDiv.innerHTML = "";

    try {

        const response = await fetch(
            `http://127.0.0.1:8000/research?company=${encodeURIComponent(company)}`
        );

        if (!response.ok) {
            throw new Error("Research request failed");
        }

        const data = await response.json();

        resultDiv.innerHTML = `
            <h3>${data.company}</h3>

            <p><strong>Sources Found</strong></p>

            ${data.sources.map(source => `
                <div class="source">
                    <p>
                        <strong>${source.title}</strong>
                    </p>

                    <p>
                        ${source.content}
                    </p>

                    <a href="${source.url}" target="_blank">
                        View Source
                    </a>
                </div>
            `).join("")}
        `;

    } catch (error) {

        resultDiv.innerHTML =
            "Could not research this company.";

        console.error(error);

    } finally {

        loadingDiv.style.display = "none";

    }
}


// 点击按钮
button.addEventListener("click", researchCompany);


// 输入框按 Enter
companyInput.addEventListener("keydown", function(event) {

    if (event.key === "Enter") {
        researchCompany();
    }

});