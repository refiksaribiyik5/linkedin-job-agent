"""PromptRegistry - dosya tabanli prompt sablonu yukleme ve render
(Roadmap M5.2, TDD Section 10 "Prompt yonetimi").

TDD Section 10: "Tum prompt sablonlari config/prompts/ altinda
versiyonlanmis Markdown dosyalari olarak tutulur (kod icine gomulmez)."
Bu modul, o dosyalari okuyup degisken yer tutucularini dolduran TEK
sorumlulugu tasir - hicbir prompt METNI burada YOKTUR, yalnizca genel
yukleme/render mantigi.

Yer tutucu mekanizmasi olarak Python'in kendi `string.Template`'i
("${degisken}" sozdizimi) kullanilir - proje talimatiyla acikca
onaylanmayan ama bu dosyaya ozgu, dusuk etki alanli bir uygulama
detayidir (M3.4'un "BeautifulSoup icin lxml yerine yerlesik
html.parser yeterli" kararindaki AYNI gerekce: ekstra bir sablon
kutuphanesi (orn. Jinja2) gerektirecek hicbir dongu/kosul burada YOK,
sadece duz degisken doldurma). "$" sozdizimi, prompt metinlerinin
dogal olarak icerebilecegi JSON ornek bloklarindaki `{`/`}` karakterleriyle
CATISMAZ - `str.format()` bu durumda kacinilmaz olarak catisirdi.

KASITLI OLARAK YAPILMAYANLAR (Roadmap'in kendi ayirdigi sonraki
milestone'larin kapsamidir): sablonlarin hangi hesaba/config surumune
bagli oldugunun cozumlenmesi (`account_config_profiles.prompt_template_refs`,
Section 15) - Faz 6/7. Bu sablonlarin fiilen bir LLM cagrisina
gonderilmesi (`LLMProviderPort.generate_structured()`) - Roadmap M5.3
(LLM Gateway).
"""

from __future__ import annotations

from pathlib import Path
from string import Template


class PromptRegistry:
    def __init__(self, prompts_dir: Path) -> None:
        self._prompts_dir = prompts_dir

    def render(self, template_name: str, **variables: str) -> str:
        template_path = self._prompts_dir / f"{template_name}.prompt.md"
        template_text = template_path.read_text(encoding="utf-8")
        return Template(template_text).substitute(**variables)
