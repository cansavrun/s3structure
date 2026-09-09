from pydantic import BaseModel, ConfigDict


class PublicResponse(BaseModel):
    # response_model yalnızca tanımlı alanları dışarı çıkarır; iç servislerin eklediği
    # bucket/role_arn gibi alanlar, iç içe modeller dahil, JSON'a taşınmaz.
    # strict=True, örneğin dosya boyutundaki "123" yazısını sessizce sayıya çevirmez.
    model_config = ConfigDict(extra="ignore", strict=True, hide_input_in_errors=True)
