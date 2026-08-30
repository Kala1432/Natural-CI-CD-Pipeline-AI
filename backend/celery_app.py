import os
from celery import Celery

def make_celery(app_name=__name__):
    redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
    
    celery = Celery(
        app_name,
        backend=redis_url,
        broker=redis_url,
        include=[
            'backend.services.analyze_service', 
            'backend.services.ai_service',
            'backend.services.simulation_service',
            'backend.services.deployment_service'
        ]
    )
    
    celery.conf.update(
        task_serializer='json',
        accept_content=['json'],  
        result_serializer='json',
        timezone='UTC',
        enable_utc=True,
    )
    
    return celery

celery_app = make_celery()
