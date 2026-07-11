"""
FastAPI routes for analytics.
Uses database DAOs for aggregating career, social, and revenue data.
"""

from fastapi import APIRouter, HTTPException

from database import analytics_dao, social_dao

router = APIRouter()


@router.get("/career")
async def get_career_analytics():
    """Get career search funnel analytics from the database."""
    try:
        # Compute from live data
        funnel = await analytics_dao.compute_funnel_summary()
        # Also get the latest snapshot if available
        snapshot = await analytics_dao.get_latest_career_snapshot()
        # Get activity log for recent job-related events
        recent_activity = await analytics_dao.get_recent_activity(limit=10)
        job_activity = [a for a in recent_activity if a.get("type") in ("job", "notification")]

        return {
            "funnel": funnel,
            "snapshot": snapshot,
            "recent_activity": job_activity,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/social")
async def get_social_analytics():
    """Get social media performance analytics from the database."""
    try:
        snapshots = await analytics_dao.get_latest_social_snapshots()
        pipeline = await social_dao.get_pipeline_counts()
        total_revenue = await analytics_dao.get_total_revenue()

        overview = {}
        if snapshots:
            overview = {
                "platforms": [
                    {
                        "platform": s.get("platform"),
                        "followers": s.get("followers", 0),
                        "views": s.get("total_views", 0),
                        "engagement": s.get("total_engagement", 0),
                        "engagement_rate": s.get("engagement_rate", 0),
                        "videos_posted": s.get("videos_posted", 0),
                        "revenue": s.get("revenue", 0),
                    }
                    for s in snapshots
                ],
                "total_revenue": total_revenue,
            }

        return {
            "overview": overview,
            "pipeline": pipeline,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/revenue")
async def get_revenue():
    """Get revenue aggregation from the database."""
    try:
        summary = await analytics_dao.get_latest_revenue_summary()
        by_source = await analytics_dao.get_revenue_by_source()
        by_month = await analytics_dao.get_revenue_by_month()
        return {
            "summary": summary,
            "by_source": by_source,
            "by_month": by_month,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/activity")
async def get_activity(limit: int = 50, activity_type: str = ""):
    """Get recent activity log entries, optionally filtered by type."""
    try:
        activities = await analytics_dao.get_recent_activity(limit)
        if activity_type:
            activities = [a for a in activities if a.get("type") == activity_type]
        return {"activities": activities}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
