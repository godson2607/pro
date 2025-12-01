def compute_feedback_rating(item: dict) -> float:
    likes = len(item.get("likes", []))
    dislikes = len(item.get("dislikes", []))

    total = likes + dislikes
    if total == 0:
        return 2.5  # neutral rating if no feedback

    feedback_score = (likes - dislikes) / total  # -1.0 to +1.0
    rating = (feedback_score + 1) * 2.5  # normalize to 0–5

    return round(rating, 2)
