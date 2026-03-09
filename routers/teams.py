from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from models import Team
from schemas.team import TeamCreate, TeamRead

router = APIRouter(
    prefix="/teams",
    tags=["Teams"]
)

@router.post("/", response_model=TeamRead)
def create_team(team: TeamCreate, db: Session = Depends(get_db)):
    nova_team = Team(nome=team.nome)

    db.add(nova_team)
    db.commit()
    db.refresh(nova_team)

    return nova_team


@router.get("/", response_model=list[TeamRead])
def list_teams(db: Session = Depends(get_db)):
    return db.query(Team).all()


@router.delete("/{team_id}")
def delete_team(team_id: int, db: Session = Depends(get_db)):
    team = db.query(Team).filter(Team.id == team_id).first()

    if not team:
        raise HTTPException(status_code=404, detail="Team not found")

    db.delete(team)
    db.commit()

    return {"message": f"Team {team_id} deleted successfully"}