import json
from datetime import datetime
from datetime import timedelta
from datetime import timezone
from typing import cast

from fastapi import APIRouter
from fastapi import Body
from fastapi import Depends
from fastapi import HTTPException
from sqlalchemy.orm import Session

from danswer.auth.invited_users import get_invited_users
from danswer.auth.invited_users import write_invited_users
from danswer.auth.users import current_admin_user
from danswer.configs.app_configs import GENERATIVE_MODEL_ACCESS_CHECK_FREQ
from danswer.configs.app_configs import TOKEN_BUDGET_GLOBALLY_ENABLED
from danswer.configs.constants import DocumentSource
from danswer.configs.constants import ENABLE_TOKEN_BUDGET
from danswer.configs.constants import TOKEN_BUDGET
from danswer.configs.constants import TOKEN_BUDGET_SETTINGS
from danswer.configs.constants import TOKEN_BUDGET_TIME_PERIOD
from danswer.db.connector_credential_pair import get_connector_credential_pair
from danswer.db.deletion_attempt import check_deletion_attempt_is_allowed
from danswer.db.engine import get_session
from danswer.db.feedback import fetch_docs_ranked_by_boost
from danswer.db.feedback import update_document_boost
from danswer.db.feedback import update_document_hidden
from danswer.db.index_attempt import cancel_indexing_attempts_for_connector
from danswer.db.models import User
from danswer.db.users import get_user_by_email
from danswer.document_index.document_index_utils import get_both_index_names
from danswer.document_index.factory import get_default_document_index
from danswer.dynamic_configs.factory import get_dynamic_config_store
from danswer.dynamic_configs.interface import ConfigNotFoundError
from danswer.file_store.file_store import get_default_file_store
from danswer.llm.factory import get_default_llm
from danswer.llm.utils import test_llm
from danswer.server.documents.models import ConnectorCredentialPairIdentifier
from danswer.server.manage.models import BoostDoc
from danswer.server.manage.models import BoostUpdateRequest
from danswer.server.manage.models import HiddenUpdateRequest
from danswer.server.manage.models import UserByEmail
from danswer.utils.logger import setup_logger

router = APIRouter(prefix="/manage")
logger = setup_logger()

GEN_AI_KEY_CHECK_TIME = "genai_api_key_last_check_time"

"""Admin only API endpoints"""


@router.get("/admin/doc-boosts")
def get_most_boosted_docs(
    ascending: bool,
    limit: int,
    _: User | None = Depends(current_admin_user),
    db_session: Session = Depends(get_session),
) -> list[BoostDoc]:
    boost_docs = fetch_docs_ranked_by_boost(
        ascending=ascending, limit=limit, db_session=db_session
    )
    return [
        BoostDoc(
            document_id=doc.id,
            semantic_id=doc.semantic_id,
            # source=doc.source,
            link=doc.link or "",
            boost=doc.boost,
            hidden=doc.hidden,
        )
        for doc in boost_docs
    ]


@router.post("/admin/doc-boosts")
def document_boost_update(
    boost_update: BoostUpdateRequest,
    _: User | None = Depends(current_admin_user),
    db_session: Session = Depends(get_session),
) -> None:
    curr_ind_name, sec_ind_name = get_both_index_names(db_session)
    document_index = get_default_document_index(
        primary_index_name=curr_ind_name, secondary_index_name=sec_ind_name
    )

    try:
        update_document_boost(
            db_session=db_session,
            document_id=boost_update.document_id,
            boost=boost_update.boost,
            document_index=document_index,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/admin/doc-hidden")
def document_hidden_update(
    hidden_update: HiddenUpdateRequest,
    _: User | None = Depends(current_admin_user),
    db_session: Session = Depends(get_session),
) -> None:
    curr_ind_name, sec_ind_name = get_both_index_names(db_session)
    document_index = get_default_document_index(
        primary_index_name=curr_ind_name, secondary_index_name=sec_ind_name
    )

    try:
        update_document_hidden(
            db_session=db_session,
            document_id=hidden_update.document_id,
            hidden=hidden_update.hidden,
            document_index=document_index,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/admin/genai-api-key/validate")
def validate_existing_genai_api_key(
    _: User = Depends(current_admin_user),
) -> None:
    # Only validate every so often
    kv_store = get_dynamic_config_store()
    curr_time = datetime.now(tz=timezone.utc)
    try:
        last_check = datetime.fromtimestamp(
            cast(float, kv_store.load(GEN_AI_KEY_CHECK_TIME)), tz=timezone.utc
        )
        check_freq_sec = timedelta(seconds=GENERATIVE_MODEL_ACCESS_CHECK_FREQ)
        if curr_time - last_check < check_freq_sec:
            return
    except ConfigNotFoundError:
        # First time checking the key, nothing unusual
        pass

    try:
        llm = get_default_llm(timeout=10)
    except ValueError:
        raise HTTPException(status_code=404, detail="LLM not setup")

    error = test_llm(llm)
    if error:
        raise HTTPException(status_code=400, detail=error)

    # Mark check as successful
    curr_time = datetime.now(tz=timezone.utc)
    kv_store.store(GEN_AI_KEY_CHECK_TIME, curr_time.timestamp())


@router.post("/admin/deletion-attempt")
def create_deletion_attempt_for_connector_id(
    connector_credential_pair_identifier: ConnectorCredentialPairIdentifier,
    _: User = Depends(current_admin_user),
    db_session: Session = Depends(get_session),
) -> None:
    from danswer.background.celery.celery import cleanup_connector_credential_pair_task

    connector_id = connector_credential_pair_identifier.connector_id
    credential_id = connector_credential_pair_identifier.credential_id

    cc_pair = get_connector_credential_pair(
        db_session=db_session,
        connector_id=connector_id,
        credential_id=credential_id,
    )
    if cc_pair is None:
        raise HTTPException(
            status_code=404,
            detail=f"Connector with ID '{connector_id}' and credential ID "
            f"'{credential_id}' does not exist. Has it already been deleted?",
        )

    # Cancel any scheduled indexing attempts
    cancel_indexing_attempts_for_connector(
        connector_id=connector_id, db_session=db_session, include_secondary_index=True
    )

    # Check if the deletion attempt should be allowed
    deletion_attempt_disallowed_reason = check_deletion_attempt_is_allowed(
        connector_credential_pair=cc_pair, db_session=db_session
    )
    if deletion_attempt_disallowed_reason:
        raise HTTPException(
            status_code=400,
            detail=deletion_attempt_disallowed_reason,
        )

    cleanup_connector_credential_pair_task.apply_async(
        kwargs=dict(connector_id=connector_id, credential_id=credential_id),
    )

    if cc_pair.connector.source == DocumentSource.FILE:
        connector = cc_pair.connector
        file_store = get_default_file_store(db_session)
        for file_name in connector.connector_specific_config["file_locations"]:
            file_store.delete_file(file_name)


@router.get("/admin/token-budget-settings")
def get_token_budget_settings(_: User = Depends(current_admin_user)) -> dict:
    if not TOKEN_BUDGET_GLOBALLY_ENABLED:
        raise HTTPException(
            status_code=400, detail="Token budget is not enabled in the application."
        )

    try:
        settings_json = cast(
            str, get_dynamic_config_store().load(TOKEN_BUDGET_SETTINGS)
        )
        settings = json.loads(settings_json)
        return settings
    except ConfigNotFoundError:
        raise HTTPException(status_code=404, detail="Token budget settings not found.")


@router.put("/admin/token-budget-settings")
def update_token_budget_settings(
    _: User = Depends(current_admin_user),
    enable_token_budget: bool = Body(..., embed=True),
    token_budget: int = Body(..., ge=0, embed=True),  # Ensure non-negative
    token_budget_time_period: int = Body(..., ge=1, embed=True),  # Ensure positive
) -> dict[str, str]:
    # Prepare the settings as a JSON string
    settings_json = json.dumps(
        {
            ENABLE_TOKEN_BUDGET: enable_token_budget,
            TOKEN_BUDGET: token_budget,
            TOKEN_BUDGET_TIME_PERIOD: token_budget_time_period,
        }
    )

    # Store the settings in the dynamic config store
    get_dynamic_config_store().store(TOKEN_BUDGET_SETTINGS, settings_json)
    return {"message": "Token budget settings updated successfully."}


@router.put("/admin/users")
def bulk_invite_users(
    emails: list[str] = Body(..., embed=True),
    _: User | None = Depends(current_admin_user),
) -> int:
    all_emails = list(set(emails) | set(get_invited_users()))
    return write_invited_users(all_emails)


@router.patch("/admin/remove-invited-user")
def remove_invited_user(
    user_email: UserByEmail,
    _: User | None = Depends(current_admin_user),
) -> int:
    user_emails = get_invited_users()
    remaining_users = [user for user in user_emails if user != user_email.user_email]
    return write_invited_users(remaining_users)


@router.patch("/admin/deactivate-user")
def deactivate_user(
    user_email: UserByEmail,
    current_user: User = Depends(current_admin_user),
    db_session: Session = Depends(get_session),
) -> None:
    if current_user.email == user_email.user_email:
        raise HTTPException(status_code=400, detail="You cannot deactivate yourself")

    user_to_deactivate = get_user_by_email(
        email=user_email.user_email, db_session=db_session
    )

    if not user_to_deactivate:
        raise HTTPException(status_code=404, detail="User not found")

    if user_to_deactivate.is_active is False:
        logger.warning("{} is already deactivated".format(user_to_deactivate.email))

    user_to_deactivate.is_active = False
    db_session.add(user_to_deactivate)
    db_session.commit()


@router.patch("/admin/activate-user")
def activate_user(
    user_email: UserByEmail,
    _: User | None = Depends(current_admin_user),
    db_session: Session = Depends(get_session),
) -> None:
    user_to_activate = get_user_by_email(
        email=user_email.user_email, db_session=db_session
    )
    if not user_to_activate:
        raise HTTPException(status_code=404, detail="User not found")

    if user_to_activate.is_active is True:
        logger.warning("{} is already activated".format(user_to_activate.email))

    user_to_activate.is_active = True
    db_session.add(user_to_activate)
    db_session.commit()
