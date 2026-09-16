from backend.app.models import ConvertRequest
from backend.app.provider import MockSemanticProvider
from backend.app.service import HarnessService


async def test_full_conversion_returns_expression_and_twelve_settings():
    service = HarnessService(MockSemanticProvider())
    response = await service.convert(
        ConvertRequest(
            strategy=(
                "최근 5일 동안 가격이 많이 떨어진 종목을 매수한다. "
                "거래량이 최근 20일 평균보다 1.5배 이상일 때만 거래하고 산업별로 중립화한다."
            )
        )
    )
    assert response.status == "PASS"
    assert response.fastExpression is not None
    assert len(response.simulationSettings) == 12
    assert response.simulationSettings["neutralization"] == "INDUSTRY"
    assert response.settingsSource["neutralization"] == "user"
    assert response.confidence == 1.0

