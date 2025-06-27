from models import FormField

# Create a new Python module that uses the FormField class to define FORMS in a cleaner way



#validate_serial = lambda v: (3000 <= int(v) <= 3050, "Must be between 3000 and 3050") if v and v.isdigit() else (False, "Must be an integer between 3000 and 3050")

def validate_serial(v):
    if v and v.isdigit():
        valid = 3000 <= int(v) <= 3050
        return valid, "Must be between 3000 and 3050" if valid else "Must be between 3000 and 3050"
    return False, "Must be an integer between 3000 and 3050"



def field_to_dict(field: FormField):
    return {
        "name": field.name,
        "label": field.label,
        "type_field": field.type_field,
        "validate": field.validate,
        "display_history": field.display_history,
        "help_text": field.help_text,
        "help_link": field.help_link,
    }


# Define FORMS_NON_DICT using the updated FormField class

FORMS_NON_DICT = [
    {
        "name": "hardware_test",
        "label": "Hardware Test",
        "fields": [
            FormField.integer("CM_serial", "CM Serial number", validate=validate_serial),
            FormField.boolean("passed_visual", "Passed Visual Inspection"),
            FormField.text("comments", "Comments"),
            FormField.boolean(
                "test_help",
                "Testing help",
                help_text="this is the help text i am typing so so soso" * 30 + " mcuh:(",
                help_link="https://google.com"
            ),
        ]
    },
    {
        "name": "power_test",
        "label": "Power Test",
        "fields": [
            FormField.null("powertesttext", "Voltages should be around 11.5 - 12.5 V, Currents 0.5 - 2.0 A"),
            FormField.blank(),
            FormField.float("management_power", "Management Power"),
            FormField.float("power_supply_voltage", "Power Supply Voltage (V) when 3.3 V becomes good"),
            FormField.float("current_draw", "Current Draw (mA) at 3.3 V"),
            FormField.boolean("mcu_programmed", "MCU Programmed Successfully"),
            FormField.boolean("test_help2", "Testing help", help_text="this is the help text2", help_link="https://prossernet.com"),
        ]
    },
    {
        "name": "i2c_tests",
        "label": "I2C Tests",
        "fields": [
            FormField.boolean("i2c_to_dcdc", "I2C to DC-DC Converter Passed"),
            FormField.boolean("dcdc_converter_test", "All DC-DC Converters Passed"),
            FormField.boolean("i2c_to_clockchips", "Clock Chips I2C Test Passed"),
            FormField.boolean("i2c_to_fpgas", "I2C to FPGA's Passed"),
            FormField.boolean("i2c_to_firefly_bank1", "I2C to FireFly Bank 1 Passed"),
            FormField.boolean("i2c_to_firefly_bank2", "I2C to FireFly Bank 2 Passed"),
            FormField.boolean("i2c_to_eeprom", "I2C to EEPROM Passed"),
        ]
    },
    {
        "name": "second_step_mcu_test",
        "label": "Second-Step MCU Test",
        "fields": [
            FormField.null("second_step_instruction", "Set FireFly transmit switches to the 3.3v position and load second step code, (clock output sent through front panel connector)"),
            FormField.float("fpga_oscillator_clock_1", "FPGA Oscillator Clock Frequency 1 (MHz)"),
            FormField.float("fpga_oscillator_clock_2", "FPGA Oscillator Clock Frequency 2 (MHz)"),
            FormField.boolean("fpga_flash_memory", "FPGA Flash Memory Test"),
        ]
    },
    {
        "name": "link_test",
        "label": "Link Integrity Testing",
        "fields": [
            FormField.null("fpga_second_step_tip", "Load the second-step FPGA code to test FPGA-FPGA and MCU-FPGA connections"),
            FormField.boolean("ibert_test", "IBERT link Test Passed"),
            FormField.file("ibert_test_upload", "Upload IBERT Test Results"),
            FormField.boolean("full_link_test", "Firefly, FPGA-FPGA, C2C, and TCDS Links Passed"),
            FormField.file("firefly_test_upload", "Upload Firefly Test Results"),
        ]
    },
    {
        "name": "manual_link_testing",
        "label": "Manual Link Testing",
        "fields": [
            FormField.null("manual_test_tip_1", "Remove the board from the test stand. Remove the FireFly devices and loopback cables. Install the proper FireFly configuraton for the end use."),
            FormField.blank(),
            FormField.null("manual_test_tip_2", "Set the FireFly transmit voltage switches to 3.8v for 25Gx12 transmitters. Install the FireFly heatsink. Route FireFly cables to the front panel. Install loopback connectors"),
            FormField.blank(),
            FormField.null("manual_test_tip_3", "Connect the CM to the golden SM. Install the SM front panel board. Attach a front panel, and connect the handle switch. Install covers. Install the board in an ATCA shelf and apply power."),
            FormField.blank(),
            FormField.null("manual_test_tip_4", "Load MCU code and configure clock chips for normal operation, then load the thrid step FPGA code"),
            FormField.blank(),
            FormField.boolean("third_step_fpga_test", "Thrid Step FPGA Test Passed"),
        ]
    },
    {
        "name": "heating_tests",
        "label": "Heating Testing",
        "fields": [
            FormField.boolean("heating_test", "Heater Tests Passed With Sufficent Cooling"),
            FormField.null("heating_tip", "Remove the CM/SM from the ATCA shelf. Remove the FireFly loopback connectors. Separate the CM from the SM. Pack the CM for shipping"),
            FormField.blank(),
            FormField.blank(),
        ]
    },
    {
        "name": "report_upload",
        "label": "Upload Test Report",
        "fields": [
            FormField.file("test_report", "Upload PDF"),
        ]
    },
]


FORMS = [
    {
        "name": f["name"],
        "label": f["label"],
        "fields": [field_to_dict(field) for field in f["fields"]],
    }
    for f in FORMS_NON_DICT
]
