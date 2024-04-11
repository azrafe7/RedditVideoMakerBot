import translators
from translators.server import tss, ApiKwargsType
import re

from typing import Optional, Union, Tuple, List

# modified version of translators.translate_html() that doesn't use multiprocessing
def translate_html(html_text: str,
                   translator: str = 'bing',
                   from_language: str = 'auto',
                   to_language: str = 'en',
                   if_use_preacceleration: bool = False,
                   **kwargs: ApiKwargsType,
                   ) -> str:
    """
    Translate the displayed content of html without changing the html structure.
    :param html_text: str, must.
    :param translator: str, default 'bing'.
    :param from_language: str, default 'auto'.
    :param to_language: str, default 'en'.
    :param if_use_preacceleration: bool, default False.
    :param **kwargs:
            :param is_detail_result: bool, default False.
            :param professional_field: str, support alibaba(), baidu(), caiyun(), cloudTranslation(), elia(), sysTran(), youdao(), volcEngine() only.
            :param timeout: float, default None.
            :param proxies: dict, default None.
            :param sleep_seconds: float, default 0.
            :param update_session_after_freq: int, default 1000.
            :param update_session_after_seconds: float, default 1500.
            :param if_use_cn_host: bool, default False. Support google(), bing() only.
            :param reset_host_url: str, default None. Support google(), argos(), yandex() only.
            :param if_check_reset_host_url: bool, default True. Support google(), yandex() only.
            :param if_ignore_empty_query: bool, default True.
            :param if_ignore_limit_of_length: bool, default False.
            :param limit_of_length: int, default 20000.
            :param if_show_time_stat: bool, default False.
            :param show_time_stat_precision: int, default 2.
            :param if_print_warning: bool, default True.
            :param lingvanex_model: str, default 'B2C', choose from ("B2C", "B2B").
            :param myMemory_mode: str, default "web", choose from ("web", "api").
    :return: str
    """

    if not tss.pre_acceleration_label and if_use_preacceleration:
        _ = tss.preaccelerate()

    def _translate_text(sentence: str) -> Tuple[str, str]:
        return sentence, tss.translators_dict[translator](query_text=sentence, from_language=from_language, to_language=to_language, **kwargs)

    pattern = re.compile('>([\\s\\S]*?)<')  # not perfect
    sentence_list = list(set(pattern.findall(html_text)))

    result_list = []
    for sentence in sentence_list:
      result = _translate_text(sentence)
      result_list.append(result)

    result_dict = {text: f'>{ts_text}<' for text, ts_text in result_list}
    _get_result_func = lambda k: result_dict.get(k.group(1), '')
    return pattern.sub(repl=_get_result_func, string=html_text)