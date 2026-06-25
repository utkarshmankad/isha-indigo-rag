"""
DGCA (Directorate General of Civil Aviation) guidelines applicable to all Indian airlines.
These documents are tagged airline="dgca" and are included in retrieval for any airline query,
ensuring passengers always receive authoritative regulatory context.
"""

DOCUMENTS = [
    {
        "id": "DGCA-001",
        "airline": "dgca",
        "title": "DGCA Passenger Rights — Flight Cancellations",
        "category": "flight_delays_and_cancellations",
        "department": "Regulatory",
        "doc_type": "regulatory",
        "last_updated": "2024-08-01",
        "content": (
            "DGCA Civil Aviation Requirement — Passenger Rights for Flight Cancellations\n\n"
            "Source: CAR Section 3, Air Transport, Series M, Part IV (amended)\n\n"
            "This CAR applies to all scheduled airlines operating within India and on routes "
            "to/from India. It establishes minimum passenger rights that airlines must comply with.\n\n"
            "Flight Cancellation Rights:\n"
            "When an airline cancels a flight, regardless of fare type, the affected passenger "
            "is entitled to:\n\n"
            "1. Full Refund: The airline must refund the full ticket price (including taxes and "
            "fees) to the original payment instrument within 7 days of the cancellation.\n\n"
            "2. Alternative Transportation: The airline must offer the passenger rebooking on "
            "the next available flight to the same destination at no additional cost, on its "
            "own services or a partner airline.\n\n"
            "3. Care and Assistance: If the alternative transportation departs more than 24 "
            "hours after the original departure, the airline must provide:\n"
            "   • Hotel accommodation (single room)\n"
            "   • Meals and refreshments\n"
            "   • Transportation between the airport and hotel\n\n"
            "Advance Cancellation Notice:\n"
            "If an airline cancels a flight at least 2 weeks before departure and notifies the "
            "passenger, the passenger is entitled to a full refund or rebooking but not "
            "necessarily to the accommodation and meal entitlements above.\n\n"
            "If a flight is cancelled with less than 2 weeks' notice, the passenger is entitled "
            "to all three categories of assistance listed above.\n\n"
            "Extraordinary Circumstances:\n"
            "Airlines are not liable for compensation beyond the refund and rebooking obligation "
            "in cases of extraordinary circumstances beyond their control, such as severe "
            "weather, political instability, air traffic control decisions, or security alerts, "
            "provided the airline took all reasonable measures to avoid the cancellation."
        ),
    },
    {
        "id": "DGCA-002",
        "airline": "dgca",
        "title": "DGCA Passenger Rights — Flight Delays",
        "category": "flight_delays_and_cancellations",
        "department": "Regulatory",
        "doc_type": "regulatory",
        "last_updated": "2024-08-01",
        "content": (
            "DGCA Civil Aviation Requirement — Passenger Rights for Flight Delays\n\n"
            "Source: CAR Section 3, Air Transport, Series M, Part IV\n\n"
            "Minimum Entitlements During Delays:\n\n"
            "Delay of 2 hours or more but less than 4 hours:\n"
            "• The airline must provide passengers with refreshments and meal vouchers "
            "appropriate to the time of day.\n"
            "• Passengers must be kept informed of the delay and its expected duration.\n\n"
            "Delay of 4 hours or more but less than 6 hours:\n"
            "• Refreshments and meal vouchers as above.\n"
            "• One free short messaging service (SMS) or email or phone call to notify a "
            "contact of choice.\n"
            "• The airline must inform passengers of their right to a refund if they no longer "
            "wish to travel.\n\n"
            "Delay exceeding 6 hours (overnight delay):\n"
            "• Where the new departure is not before 1:00 AM the following morning, or where "
            "the passenger cannot travel to their onward destination without overnight stay:\n"
            "  - Hotel accommodation (single occupancy) at or near the airport\n"
            "  - Meals at the hotel or meal vouchers\n"
            "  - Transport between the airport and the hotel\n\n"
            "Delay exceeding 8 hours:\n"
            "• The airline must offer the passenger the choice of a full ticket refund "
            "in lieu of continued travel on the delayed flight.\n\n"
            "These entitlements arise from DGCA regulations and are in addition to any "
            "commercial arrangements the airline may offer. Passengers may file complaints "
            "on the DGCA AirSewa portal if these rights are denied."
        ),
    },
    {
        "id": "DGCA-003",
        "airline": "dgca",
        "title": "DGCA Denied Boarding Compensation",
        "category": "flight_delays_and_cancellations",
        "department": "Regulatory",
        "doc_type": "regulatory",
        "last_updated": "2024-08-01",
        "content": (
            "DGCA Civil Aviation Requirement — Denied Boarding Compensation\n\n"
            "Source: CAR Section 3, Air Transport, Series M, Part IV\n\n"
            "Scope:\n"
            "This requirement applies when an airline involuntarily denies boarding to a "
            "confirmed passenger who has checked in by the required deadline, due to "
            "overbooking or operational reasons.\n\n"
            "Voluntary Denied Boarding:\n"
            "Airlines must first call for volunteers willing to give up their seat in exchange "
            "for agreed benefits. The airline and volunteer must agree on the compensation "
            "before the volunteer surrenders their seat.\n\n"
            "Involuntary Denied Boarding — Mandatory Compensation:\n"
            "When an airline must involuntarily deny boarding, the following compensation "
            "must be paid immediately in addition to the right to refund or rebooking:\n\n"
            "For flights scheduled block time up to 1 hour:\n"
            "• ₹5,000 if rebooked arriving within 1 hour of original arrival time.\n"
            "• ₹10,000 if final destination arrival is delayed by more than 1 hour.\n\n"
            "For flights scheduled block time 1–2 hours:\n"
            "• ₹7,500 if rebooked arriving within 1 hour of original arrival time.\n"
            "• ₹10,000 if final destination arrival is delayed by more than 1 hour.\n\n"
            "For flights scheduled block time exceeding 2 hours:\n"
            "• ₹10,000 if rebooked arriving within 2 hours of original arrival time.\n"
            "• ₹20,000 if final destination arrival is delayed by more than 2 hours.\n\n"
            "Additional Entitlements:\n"
            "In all cases of involuntary denied boarding, the passenger is also entitled to:\n"
            "• Meals and refreshments proportionate to the waiting period\n"
            "• Hotel accommodation if overnight stay is required\n"
            "• Transportation to/from the hotel\n"
            "• One phone call or SMS notification\n\n"
            "Compensation must be paid immediately at the airport, not as vouchers or miles "
            "unless the passenger specifically agrees."
        ),
    },
    {
        "id": "DGCA-004",
        "airline": "dgca",
        "title": "DGCA Tarmac Delay Rules",
        "category": "flight_delays_and_cancellations",
        "department": "Regulatory",
        "doc_type": "regulatory",
        "last_updated": "2024-08-01",
        "content": (
            "DGCA Tarmac Delay Requirements for Indian Airlines\n\n"
            "Source: DGCA Circular, Tarmac Delay Guidelines\n\n"
            "Tarmac delays refer to situations where passengers are held on an aircraft on the "
            "ground (at the gate or on the apron/tarmac) without taking off.\n\n"
            "Passenger Entitlements During Tarmac Delays:\n\n"
            "30 minutes into tarmac delay:\n"
            "• The pilot-in-command must inform passengers of the delay, its cause, and the "
            "expected departure time. Information must be updated every 30 minutes thereafter.\n\n"
            "After 2 hours on tarmac:\n"
            "• Airlines must provide drinking water and snacks or light meals to passengers.\n"
            "• Toilets must be operational and accessible.\n"
            "• Ventilation and cabin temperature must be maintained within comfortable limits.\n\n"
            "After 4 hours on tarmac:\n"
            "• The aircraft must return to the terminal gate to allow passengers to disembark, "
            "unless the pilot-in-command determines that safety or air traffic control "
            "requirements prevent this.\n"
            "• Passengers who disembark must be offered rebooking on the next available flight "
            "or a full refund.\n\n"
            "Exceptions:\n"
            "The 4-hour disembarkation requirement does not apply if the pilot-in-command, "
            "in consultation with the airline operations control centre and air traffic control, "
            "determines that take-off is imminent (within 30 minutes).\n\n"
            "Complaint Mechanism:\n"
            "Passengers who believe their tarmac delay rights have been violated may file a "
            "complaint with the DGCA through the AirSewa portal at complaints.airsewa.gov.in "
            "or by calling the AirSewa helpline at 1800-11-1351."
        ),
    },
    {
        "id": "DGCA-005",
        "airline": "dgca",
        "title": "DGCA Baggage Liability — Montreal Convention",
        "category": "baggage",
        "department": "Regulatory",
        "doc_type": "regulatory",
        "last_updated": "2024-08-01",
        "content": (
            "DGCA and Montreal Convention — Baggage Liability Limits\n\n"
            "India is a signatory to the Montreal Convention 1999 (MC99), which governs "
            "the liability of airlines for damage, delay, destruction, or loss of baggage "
            "on international flights.\n\n"
            "Liability Limits under Montreal Convention:\n"
            "• Checked baggage: Up to 1,288 Special Drawing Rights (SDR) per passenger for "
            "destruction, loss, damage, or delay of checked baggage. The SDR equivalent in "
            "Indian Rupees varies; approximate equivalent is ₹1,40,000–₹1,60,000 depending "
            "on prevailing exchange rates.\n"
            "• Cabin baggage: Up to 1,288 SDR per passenger for damage caused by the airline's "
            "fault.\n"
            "• These limits may be exceeded by making a special declaration of interest (SDI) "
            "before the flight, subject to the airline's supplementary charge.\n\n"
            "Domestic Flight Baggage Liability:\n"
            "For domestic Indian flights (not covered by MC99), liability limits are governed "
            "by the Carriage by Air Act, 1972 and applicable airline-specific conditions of "
            "carriage. Airlines typically limit liability to ₹200 per kg for checked baggage "
            "on domestic routes unless a higher value is declared and an additional premium paid.\n\n"
            "Reporting Damaged or Lost Baggage:\n"
            "Passengers must report baggage irregularities before leaving the airport arrival hall "
            "by filing a Property Irregularity Report (PIR) at the airline's baggage services "
            "counter. Filing a PIR is a precondition for making a claim. Claims for damaged "
            "baggage must be made in writing within 7 days of receipt. Claims for delayed "
            "baggage must be made within 21 days of receipt. Claims for lost baggage must be "
            "filed within 2 years of the date the aircraft arrived at the destination."
        ),
    },
    {
        "id": "DGCA-006",
        "airline": "dgca",
        "title": "DGCA Complaint Mechanism and AirSewa Portal",
        "category": "flight_delays_and_cancellations",
        "department": "Regulatory",
        "doc_type": "regulatory",
        "last_updated": "2024-08-01",
        "content": (
            "DGCA Passenger Complaint Mechanism — AirSewa Portal\n\n"
            "The DGCA operates the AirSewa portal as a centralised grievance redressal mechanism "
            "for airline passengers in India.\n\n"
            "How to File a Complaint:\n"
            "1. Visit complaints.airsewa.gov.in or call the AirSewa helpline at 1800-11-1351 "
            "(toll-free).\n"
            "2. Register as a user and submit the complaint with supporting documentation "
            "(booking reference, correspondence with airline, receipts).\n"
            "3. The DGCA Nodal Officer will acknowledge the complaint within 24 hours and "
            "forward it to the concerned airline for resolution.\n"
            "4. Airlines are required to respond to DGCA within 15 days with an update on "
            "the passenger's complaint.\n\n"
            "Types of Complaints Handled:\n"
            "• Flight delays and cancellations (denial of entitlements)\n"
            "• Denied boarding without adequate compensation\n"
            "• Baggage loss, damage, or delay\n"
            "• Failure to provide special assistance (wheelchair, UM)\n"
            "• Refund delays beyond 7 days\n"
            "• Misleading advertising or pricing by airlines\n"
            "• Conduct of airline staff\n\n"
            "Escalation:\n"
            "If the airline does not resolve the complaint within 30 days, the passenger "
            "may escalate to the DGCA's Consumer Grievance Cell. The DGCA may impose "
            "penalties on airlines for systemic non-compliance with CAR provisions.\n\n"
            "For urgent safety-related complaints, contact the DGCA Flight Standards "
            "Directorate at dgca@nic.in or visit www.dgca.gov.in."
        ),
    },
    {
        "id": "DGCA-007",
        "airline": "dgca",
        "title": "DGCA and IATA Dangerous Goods Regulations",
        "category": "safety_and_security",
        "department": "Regulatory",
        "doc_type": "regulatory",
        "last_updated": "2024-08-01",
        "content": (
            "DGCA Dangerous Goods Regulations for Passengers\n\n"
            "All airlines operating in India must follow the IATA Dangerous Goods Regulations "
            "(DGR) and DGCA Safety Instructions on the carriage of hazardous materials.\n\n"
            "Lithium Battery Rules (Applicable to All Indian Airlines):\n"
            "The following rules apply uniformly across all Indian carriers:\n\n"
            "Lithium-Ion Batteries (rechargeable — phones, laptops, power banks):\n"
            "• Must be carried in carry-on baggage. Not permitted in checked baggage as spare "
            "batteries.\n"
            "• Up to 100 Wh: No limit on quantity in carry-on.\n"
            "• 100 Wh to 160 Wh: Maximum 2 per passenger; airline approval required.\n"
            "• Above 160 Wh: Prohibited on passenger aircraft (cargo-only operations apply).\n"
            "• Power banks: Must be in carry-on only. Must not be used or charged during flight "
            "if stowed in overhead bin.\n\n"
            "Lithium Metal Batteries (non-rechargeable — watch batteries, camera batteries):\n"
            "• Up to 2 g lithium content: Unlimited in cabin.\n"
            "• 2–8 g lithium content: Maximum 2 in checked or carry-on baggage.\n\n"
            "E-Cigarettes and Vaping Devices:\n"
            "Across all Indian airlines: E-cigarettes and vaping devices must be carried in "
            "carry-on baggage only. Cannot be charged on the aircraft. Cannot be used anywhere "
            "on the aircraft. Liquids subject to 100 ml cabin liquid restriction.\n\n"
            "Other Commonly Queried Items:\n"
            "• Gas cartridges (camping stoves): Prohibited in cabin and hold if containing gas.\n"
            "• Dry ice: Max 2.5 kg per passenger in hold for perishables, with airline approval.\n"
            "• Mercury thermometers: Prohibited in checked and carry-on baggage.\n"
            "• Alcoholic beverages above 70% ABV: Prohibited.\n"
            "• Alcoholic beverages 24–70% ABV: Up to 5 litres in checked baggage.\n"
            "• Alcoholic beverages under 24% ABV: No restriction."
        ),
    },
    {
        "id": "DGCA-008",
        "airline": "dgca",
        "title": "DGCA Special Needs Passenger Rights",
        "category": "special_assistance",
        "department": "Regulatory",
        "doc_type": "regulatory",
        "last_updated": "2024-08-01",
        "content": (
            "DGCA Requirements for Passengers with Disabilities and Special Needs\n\n"
            "Source: CAR Section 3, Air Transport, Series M, Part III — Facilities to "
            "Disabled Persons and Persons with Reduced Mobility\n\n"
            "Scope:\n"
            "All Indian airlines and airports must comply with DGCA requirements to ensure "
            "accessible travel for passengers with disabilities, reduced mobility (PRM), "
            "and other special needs.\n\n"
            "Right to Assistance:\n"
            "• Airlines may NOT refuse carriage to a person solely on grounds of disability "
            "or reduced mobility, except for legitimate and justifiable safety reasons.\n"
            "• Any refusal of carriage on disability grounds must be in writing and must "
            "explain the specific safety reason.\n\n"
            "Wheelchair Assistance:\n"
            "• Airlines must provide wheelchair assistance from check-in to the aircraft seat "
            "and from the aircraft seat to the airport exit at the destination, free of charge.\n"
            "• WCHR, WCHS, and WCHC assistance categories must be honoured within the "
            "limitations of the aircraft and airport infrastructure.\n"
            "• A passenger's own wheelchair is accepted free of charge in the hold in addition "
            "to the standard baggage allowance.\n\n"
            "Notification Requirement:\n"
            "Passengers must notify the airline of their special assistance needs at least "
            "48 hours before departure to ensure adequate arrangements. Airlines should "
            "still make reasonable efforts to assist passengers who notify less than 48 hours "
            "in advance.\n\n"
            "Unaccompanied Minors:\n"
            "Airlines are required to offer a supervised Unaccompanied Minor (UM) service "
            "for children aged 5–12 years travelling alone. Airlines may charge a service "
            "fee for UM services but must ensure the child's safety and supervision throughout.\n\n"
            "Complaints:\n"
            "Passengers who are denied special assistance or refused carriage on disability "
            "grounds may file a complaint with the DGCA at complaints.airsewa.gov.in or "
            "write to the DGCA Disability Cell."
        ),
    },
]
