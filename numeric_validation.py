"""Проверка числовых полей без подмены ошибочных значений нулями."""
import numpy as np
import pandas as pd


def numeric_values(values, field, row_offset=2):
    """Пустые ячейки оставляет пустыми; непустые некорректные отклоняет."""
    blank = values.isna() | values.astype("string").str.strip().eq("").fillna(False)
    numbers = pd.to_numeric(values.mask(blank), errors="coerce")
    invalid = ~blank & (numbers.isna() | ~np.isfinite(numbers))
    if invalid.any():
        rows = [str(int(i) + row_offset) for i in values.index[invalid][:5]]
        raise ValueError(f"Столбец «{field}»: некорректное число, строка Excel/CSV: {', '.join(rows)}.")
    return numbers
