def split_message(text: str, max_length: int = 4096) -> list[str]:
    parts = []
    while text:
        if len(text) <= max_length:
            parts.append(text)
            break
        chunk = text[:max_length]
        split_pos = chunk.rfind("\n")
        if split_pos == -1:
            split_pos = chunk.rfind(" ")
        if split_pos == -1:
            split_pos = max_length
        parts.append(text[:split_pos])
        text = text[split_pos:].lstrip("\n ")
    return parts
