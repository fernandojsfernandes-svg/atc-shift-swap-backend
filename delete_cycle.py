from database import SessionLocal
from models import CycleConfirmation, CycleSwap, CycleProposal

db = SessionLocal()
cycle_id = 1  # ciclo que queres apagar

# apagar confirmações do ciclo
db.query(CycleConfirmation).filter(CycleConfirmation.cycle_id == cycle_id).delete()

# apagar swaps ligados ao ciclo
db.query(CycleSwap).filter(CycleSwap.cycle_id == cycle_id).delete()

# apagar proposta do ciclo
db.query(CycleProposal).filter(CycleProposal.id == cycle_id).delete()

db.commit()
db.close()

print("Ciclo antigo apagado com sucesso!")