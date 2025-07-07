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
        "display_form": field.display_form
    }


# Define FORMS_NON_DICT using the updated FormField class

FORMS_NON_DICT = [
    {
        "name": "hardware_test",
        "label": "Hardware Test",
        "fields": [
            FormField.integer(name="CM_serial", label="CM Serial number", validate=validate_serial),
            FormField.boolean(name="passed_visual", label="Passed Visual Inspection"),
            FormField.text(name="comments", label="Comments"),
        ]
    },
    {
        "name": "power_test",
        "label": "Power Up Test",
        "fields": [
            FormField.null(name="powertesttext", label="Voltages should be around 11.5 - 12.5 V, Currents 0.5 - 2.0 A"),
            FormField.blank(),
            FormField.float(
                name="management_power",
                label="Management Power",
                help_text="""Unpack a board. Set FireFly transmit switches to 3.8V position. Install one 4-channel FireFly
                    transceiver on each FPGA, and connect a fiber cable between them. Install copper FireFly
                    loopback cables to other FireFly sites. Connect the board to the test system. Position fans for
                    cooling. Connect a meter to measure 3.3V management power. Ramp the 12V power and note
                    the voltage level when the 3.3V becomes good. Note the current as the voltage is ramped up to
                    12V. Stop the test if certain voltage or current criteria are not met.
                    Program the MCU with first-step code and run the program.""",
                help_label="Power Up Test Instructions"
            ),
            FormField.float(name="power_supply_voltage", label="Power Supply Voltage (V) when 3.3 V becomes good"),
            FormField.float(name="current_draw", label="Current Draw (mA) at 3.3 V"),
            FormField.boolean(name="mcu_programmed", label="MCU Programmed Successfully"),
        ]
    },
    {
        "name": "second_step_mcu_test",
        "label": "Second-Step MCU Test",
        "fields": [
            FormField.null(name="second_step_instruction", label="Set FireFly transmit switches to the 3.3v position and load second step code, (clock output sent through front panel connector)"),
            FormField.float(name="fpga_oscillator_clock_1", label="FPGA Oscillator Clock Frequency 1 (MHz)"),
            FormField.help_instance(name="clock_freq_help", help_text="""
                                    Load second-step MCU code, which automatically turns on power and monitors conditions.
                                    Configure the clock chips for refclk testing. Load first-step FPGA code, which tests refclk inputs
                                    and I2C. Verify that oscillator clock is 200 MHz on each FPGA (sent out through front panel
                                    connector).""", help_label="FPGA Clock Frequency Checks"),
            FormField.float(name="fpga_oscillator_clock_2", label="FPGA Oscillator Clock Frequency 2 (MHz)"),
            FormField.boolean(
                name="fpga_flash_memory",
                label="FPGA Flash Memory Test",
                help_text="""Test optics I2C registers related to 3.3V/3.8V options. Test non-sysmon I2C to each FPGA. Verify
                            that all refclks have the expected frequency (read over I2C). Switch clock chips between different
                            inputs. Test FPGA flash memory.""",
                help_link="find link",
                help_label="Flash Memory Test - find link"
            ),
        ]
    },
    {
        "name": "link_test",
        "label": "Link Integrity Testing",
        "fields": [
            FormField.null(name="fpga_second_step_tip", label="Load the second-step FPGA code to test FPGA-FPGA and MCU-FPGA connections"),
            FormField.boolean(name="ibert_test", label="IBERT link Test Passed"),
            FormField.file(name="ibert_test_upload", label="Upload IBERT Test Results"),
            FormField.boolean(name="full_link_test", label="Firefly, FPGA-FPGA, C2C, and TCDS Links Passed"),
            FormField.file(name="firefly_test_upload", label="Upload Firefly Test Results"),
        ]
    },
    {
        "name": "manual_link_testing",
        "label": "Manual Link Testing",
        "fields": [
            FormField.null(name="manual_test_tip_1", label="Remove the board from the test stand. Remove the FireFly devices and loopback cables. Install the proper FireFly configuration for the end use."),
            FormField.blank(),
            FormField.null(name="manual_test_tip_2", label="Set the FireFly transmit voltage switches to 3.8v for 25Gx12 transmitters. Install the FireFly heatsink. Route FireFly cables to the front panel. Install loopback connectors"),
            FormField.blank(),
            FormField.null(name="manual_test_tip_3", label="Connect the CM to the golden SM. Install the SM front panel board. Attach a front panel, and connect the handle switch. Install covers. Install the board in an ATCA shelf and apply power."),
            FormField.blank(),
            FormField.null(name="manual_test_tip_4", label="Load MCU code and configure clock chips for normal operation, then load the third step FPGA code"),
            FormField.blank(),
            FormField.boolean(name="third_step_fpga_test", label="Third Step FPGA Test Passed"),
        ]
    },
    {
        "name": "heating_tests",
        "label": "Heating Testing",
        "fields": [
            FormField.boolean(name="heating_test", label="Heater Tests Passed With Sufficient Cooling"),
            FormField.null(name="heating_tip", label="Remove the CM/SM from the ATCA shelf. Remove the FireFly loopback connectors. Separate the CM from the SM. Pack the CM for shipping"),
            FormField.blank(),
            FormField.blank(),
        ]
    },
    {
        "name": "report_upload",
        "label": "Upload Test Report",
        "fields": [
            FormField.file(name="test_report", label="Upload PDF"),
        ]
    },
    {
        "name": "i2c_tests",
        "label": "I2C Tests",
        "fields": [
            FormField.boolean(
                name="i2c_to_dcdc",
                label="I2C to DC-DC Converter Passed",
                help_text="""Test I2C to each DC-DC converter (schematic 4.02)
                        Decide what to look for. We want to be able to verify that both reading and writing work
                        as we uniquely access all 7 converters. Detect if I2C switching fails and we talk to the
                        same converter multiple times. Verify that the I2C_RESET_PWR signal to the I2C mux
                        works. Report errors as encountered. Report success after communicating with all seven
                        DC-DC converters.""",
                help_link="https://github.com/apollo-lhc/cm_mcu/blob/master/projects/prod_test/CommandLineTask.c#L40",
                help_label="I2C to DC-DC Converter Test"
            ),
            FormField.boolean(
                name="dcdc_converter_test",
                label="All DC-DC Converters Passed",
                help_text="""Configure, enable, and check each DC-DC converter.
                            Configure and enable converters one at a time,
                            following the power-on sequence of schematic 1.04. Figure out how to uniquely test the paired 0.85 volt
                            converters. They are used in pairs, but we don’t know if one is good and one is bad. Check voltages and
                            currents by reading internal DC-DC converter registers and the MCU ADC. Report errors as encountered,
                            and success after enabling all seven DC-DC converters.""",
                help_link="https://github.com/apollo-lhc/cm_mcu/blob/master/projects/prod_test/CommandLineTask.c#L41",
                help_label="DCDC Converter Tests"
            ),
            FormField.float(name="dcdc_voltage", label="DC-DC Measured Voltage"),
            FormField.float(name="dcdc_current", label="DC-DC Measured Current"),
            FormField.boolean(
                name="i2c_clockchips",
                label="Clock Chips I2C Test Passed",
                help_text="""Test I2C to clock chips and I2C registers (schematic 4.03)
                            We want to be able to verify that both reading and writing work as we uniquely access
                            all 5 clock chips. Detect if I2C switching fails and we talk to the same chip multiple times.
                            Verify that we can uniquely access both register chips. Maybe toggle the “RESET” signals
                            that go to the clock chips and verify that something with the clock chips changed? Verify
                            that the I2C_RESET_CLOCKS signal to the I2C mux works. Report errors as encountered.
                            Report success after communicating with all five clock chips and both register chips.""",
                help_link="https://github.com/apollo-lhc/cm_mcu/blob/master/projects/prod_test/CommandLineTask.c#L42",
                help_label="I2C Clock Tests"
            ),
            FormField.boolean(
                name="i2c_to_fpgas",
                label="I2C to FPGA's Passed",
                help_text="""Test I2C to FPGAs (schematic 4.04)
                        (NOTE: This test requires a board that has FPGAs installed. Development of code may
                        need to be deferred. Also, only the SYSMON ports can be tested before code is loaded
                        into the FPGAs.)
                        We want to be able to verify that both reading and writing work as we uniquely access
                        each FPGA. Detect if I2C switching fails and we talk to the same FPGA multiple times.
                        Verify that the I2C_RESET_FPGAS signal to the I2C mux works. Report errors as
                        encountered. Report success after communicating with both FPGAs.""",
                help_link="https://github.com/apollo-lhc/cm_mcu/blob/master/projects/prod_test/CommandLineTask.c#L45",
                help_label="I2C to FPGA Test"
            ),
            FormField.help_instance(
                name="i2c_to_fireflies",
                help_text="""Test I2C to each FireFly bank (schematic 4.05 and 4.06)
                            (NOTE: Complete coverage for this test requires that at least 4 FireFlys are installed in
                            each bank, with two on each I2C MUX. We may choose to do what we can with a single
                            FireFly on each bank.)
                            We want to be able to verify that both reading and writing work as we uniquely access
                            different FireFly devices. Detect if I2C switching fails and we talk to the same FireFly
                            multiple times. Verify that the I2C_RESET_F1_OPTICS and I2C_RESET_F2_OPTICS signals
                            to the I2C muxes work. Verify that we can uniquely access both register chips. Maybe
                            use the PRESENT signals and the RESET signal to the FireFlys? Report errors as
                            encountered. Report success after communicating with both FPGAs.""",
                help_link="https://github.com/apollo-lhc/cm_mcu/blob/master/projects/prod_test/CommandLineTask.c#L43",
                help_label="I2C Firefly Test"
            ),
            FormField.boolean(name="i2c_to_firefly_bank1", label="I2C to FireFly Bank 1 Passed"),
            FormField.boolean(name="i2c_to_firefly_bank2", label="I2C to FireFly Bank 2 Passed"),
            FormField.boolean(
                name="i2c_to_eeprom",
                label="I2C to EEPROM Passed",
                help_text="""Test I2C to EEPROM (schematic 4.01)
                            (NOTE: We may want to program the configuration block with the board serial number
                            in this step, or that may happen elsewhere.)
                            We want to verify that we can program and read the EEPROM that is used to hold the
                            board serial number and the synthesizer configuration files. Also, that the write-protect
                            signal works.""",
                help_link="https://github.com/apollo-lhc/cm_mcu/blob/master/projects/prod_test/CommandLineTask.c#L44",
                help_label="I2C to EEPROM Test"
            ),
        ]
    }
]




FORMS = [
    {
        "name": f["name"],
        "label": f["label"],
        "fields": [field_to_dict(field) for field in f["fields"]],
    }
    for f in FORMS_NON_DICT
]