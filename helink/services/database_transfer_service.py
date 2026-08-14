class DatabaseTransferService:
    def __init__(self,database): self.database=database
    def validate(self,path): self.database.validate(path)
    def export(self,destination): return self.database.export_to(destination)
    def import_(self,source): return self.database.import_from(source)
