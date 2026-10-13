"""Prompt templates for diagram generation."""

USE_CASE = """You are a UML modeling expert.

Analyze the following Software Requirements Specification (SRS) and generate a UML Use Case Diagram using PlantUML.

Requirements:
1. Identify all relevant actors from the SRS.
2. Identify the main use cases from the functional requirements.
3. Connect each actor to the appropriate use cases.
4. Use <<include>> relationships only when one use case must always use another use case.
5. Use <<extend>> relationships only when the behavior is optional or conditional.
6. Do not invent actors or use cases that are not supported by the SRS.
7. Use clear and meaningful names for actors and use cases.
8. Place all use cases inside a system boundary.
9. A use case diagram is NOT a flowchart. Never connect two use cases with a plain arrow
   (UC1 --> UC2). Use cases may only be linked with <<include>>, <<extend>> or generalization.
10. Connect actors to use cases with a plain association (Actor --> UseCase). Never connect two actors
    with an association, and never use an actor in an <<include>> or <<extend>> relationship.
11. Arrow direction: <<include>> points FROM the base use case TO the included one (Base ..> Included : <<include>>).
    <<extend>> points FROM the optional use case TO the base one (Optional ..> Base : <<extend>>).
12. Every actor and every use case must be connected to at least one relationship. An external system
    (for example a payment gateway) is connected to the use case that uses it (UseCase --> ExternalSystem).
13. Connect an actor to the use cases it starts. Included and extending use cases do not need their own actor line.
14. Make sure the PlantUML syntax is valid.
15. Return ONLY the PlantUML code. Do not provide explanations.

Example of the correct relationship style (different system, only to show the notation):

@startuml
left to right direction
actor Member
actor Librarian
actor "SMS Service" as SMS
rectangle "Library System" {
  usecase "Login" as L1
  usecase "Borrow Book" as L2
  usecase "Renew Loan" as L3
  usecase "Manage Books" as L4
  usecase "Send Due Reminder" as L5
}
Member --> L2
Librarian --> L4
L2 ..> L1 : <<include>>
L4 ..> L1 : <<include>>
L3 ..> L2 : <<extend>>
L5 --> SMS
@enduml

SRS:

{srs}
"""

CLASS = """You are a UML modeling expert.

Analyze the following Software Requirements Specification (SRS) and generate a UML Class Diagram using PlantUML.

Requirements:
1. Identify the main classes (domain entities) from the SRS.
2. Add attributes with types and the most important methods.
3. Add associations, aggregations, compositions and generalizations only when the SRS supports them.
4. Add multiplicities to associations where they are clear from the SRS.
5. Do not invent classes that are not supported by the SRS.
6. Use clear and meaningful names (PascalCase for classes, camelCase for members).
7. Use UML notation, not Java: write attributes as "- name : Type" and methods as
   "+ name(param : Type) : ReturnType". Do not write "String name".
8. Do not repeat a related class as an attribute (no "customer : Customer"); show it with an association line.
9. Generalization: write "Parent <|-- Child". The class on the LEFT of "<|--" is the parent.
   Use it ONLY when the SRS says "is a kind of". Never use it for "has", "belongs to" or "uses".
   Never draw inheritance as an association: "Person -- Member : is a" is WRONG, write "Person <|-- Member".
   An abstract class must be the parent of at least one class.
10. Every class must be connected to at least one other class.
11. Choose the relationship from the SRS wording:
    - association with multiplicities for "has", "belongs to", "enrolls in": Customer "1" -- "0..*" Booking
    - composition when the part cannot exist without the whole ("contains", "is made of"): Hall "1" *-- "1..*" Seat
    - aggregation when the part can exist on its own ("groups", "has a set of"): Team "1" o-- "0..*" Player
    - realization when a class "implements" an interface: Notifiable <|.. Student
    - dependency when a class only "uses" another one temporarily: ReportGenerator ..> Course
    Declare interfaces with "interface Name" and fixed value lists with "enum Name { ... }".
    Never put "enum" inside a class: "class Status { enum {...} }" is WRONG.
12. Make sure the PlantUML syntax is valid.
13. Return ONLY the PlantUML code. Do not provide explanations.

Example of the correct notation (different system, only to show the notation):

@startuml
abstract class Person {
  - name : String
  - email : String
}
class Member {
  - memberId : int
  + borrow(book : Book) : Loan
}
class Librarian {
  - staffId : int
}
class Book {
  - isbn : String
  - title : String
}
class Loan {
  - loanDate : Date
  - dueDate : Date
}
class Shelf {
  - code : String
}
enum LoanStatus {
  ACTIVE
  RETURNED
  OVERDUE
}
interface Searchable {
  + search(keyword : String) : void
}
Person <|-- Member
Person <|-- Librarian
Member "1" -- "0..*" Loan : borrows
Loan "0..*" -- "1" Book : of
Loan "0..*" -- "1" LoanStatus : has
Shelf "1" *-- "0..*" Book : holds
Searchable <|.. Book
@enduml

SRS:

{srs}
"""

TEMPLATES = {"USE_CASE": USE_CASE, "CLASS": CLASS}


def generation_prompt(srs_text, diagram_type):
    # replace() instead of format(): the PlantUML example contains { } braces,
    # which format() would try to read as placeholders.
    return TEMPLATES[diagram_type].replace("{srs}", srs_text.strip())