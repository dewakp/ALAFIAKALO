"""Alembic environment configuration."""

from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool
from alembic import context

from app.core.config import settings
from app.core.database import Base

# Import all models so they register with Base.metadata
from app.models.user import User  # noqa
from app.models.nutrition import NutritionLog  # noqa
from app.models.fitness import FitnessLog  # noqa
from app.models.labs import LabResult  # noqa
from app.models.medications import Medication  # noqa
from app.models.mood import MoodEntry  # noqa
from app.models.lifestyle import LifestyleEntry  # noqa
from app.models.insurance import Insurance  # noqa
from app.models.diagnostics import DiagnosticAssessment, DifferentialDiagnosis, ScreeningRecommendation, LabCorrelationReport  # noqa
from app.models.blockchain import BlockRecord, ChainMeta  # noqa
from app.models.physicians import Physician, SavedPhysician, PhysicianReview  # noqa
from app.models.peritoneal_dialysis import PDSession, PDExchange  # noqa
from app.models.advanced_directives import AdvancedDirective  # noqa
from app.models.data_sharing import DataGrant, DataShareInvitation  # noqa
from app.models.wellness import WellnessScore, MealPlan, ExercisePlan  # noqa
from app.models.system_id import SystemIdLog  # noqa
from app.models.chronic_conditions import ClinicalNote  # noqa

config = context.config
config.set_main_option("sqlalchemy.url", settings.DATABASE_URL_SYNC)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(url=url, target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
