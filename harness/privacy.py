"""Personal items (rule 10) are masked on screen: the server does not send their title until she clicks.

What the board shows instead is a generic label and the date. The details (title, project code, person)
come only from the reveal endpoint, one item at a time."""

LABELS = {"task": "Personal task", "deadline": "Personal task", "waiting_on": "Personal follow-up", "email": "Personal email", "note": "Personal note"}


def label(item_type: str) -> str:
    return LABELS[item_type]


def is_personal(space: str | None) -> bool:
    return space == "personal"
