import re
from typing import Tuple, List, Dict, Any

def resolve_state(raw_text: str) -> Tuple[str, List[Dict[str, Any]]]:
    pattern = r'\[(TIME_UPDATE|STAT_UPDATE|LOCATION_UPDATE):\s*([^\]]+)\]'
    updates = []
    def replacer(match):
        updates.append({"type": match.group(1), "payload": match.group(2).strip()})
        return ""
    clean_text = re.sub(pattern, replacer, raw_text).strip()
    return clean_text, updates
