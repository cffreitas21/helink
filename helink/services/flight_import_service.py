from helink.services.garmin_file_parser import parse_files

class FlightImportService:

    def __init__(self,flights): self.flights=flights

    def import_for_aircraft(self,paths,aircraft_id):
        parsed=parse_files(paths,aircraft_id)

        for flight in parsed:self.flights.save(flight)
        return len(parsed)

    def add_to_flight(self,paths,flight_id,file_type):

        existing=self.flights.find_by_id(flight_id)
        parsed=parse_files(paths,existing.aircraft_id,file_type)

        for flight in parsed:
            flight['flight_date']=existing.flight_date; flight['departure_time']=existing.departure_time
            flight['origin']=existing.origin; flight['destination']=existing.destination
            self.flights.save(flight)
        return len(parsed)
