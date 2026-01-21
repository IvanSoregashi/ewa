from collections.abc import Callable

from rapidfuzz import fuzz


def group_by_score(all_data: list[str], key: Callable, score: int):
    page_list = []
    used_list = []

    for i, data in enumerate(all_data):
        if i not in used_list:
            lis = []

            for j, sec_data in enumerate(all_data):
                isTrue = []

                for k in range(len(key(all_data[0]))):
                    first_text = key(data)[k]
                    sec_text = key(sec_data)[k]

                    if isinstance(first_text, str) and isinstance(sec_text, str):
                        isTrue.append(fuzz.partial_ratio(first_text.lower(), sec_text.lower()) > score)
                    elif isinstance(first_text, int) and isinstance(sec_text, int):
                        isTrue.append(first_text == sec_text)

                if all(isTrue) and i not in page_list and j not in page_list:
                    lis.append(j)
                    used_list.append(j)

            non_page_list = sorted(set(lis))

            if len(non_page_list) > 1:
                page_list.extend(non_page_list)
                all_page_list = [all_data[pg] for pg in non_page_list]
                yield key(data), all_page_list
            else:
                yield key(data), [data]

