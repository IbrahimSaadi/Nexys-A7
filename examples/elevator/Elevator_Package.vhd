library IEEE;
use IEEE.STD_LOGIC_1164.ALL;

package Elevator_Package is

    component clk_div
        port (
            clk, rst, restart : in std_logic;
            tick_1hz : out std_logic
        );
    end component;

    component fsm
        port (
            clk, rst, go_pulse, tick_1hz : in std_logic;
            dest_floor : in std_logic_vector(3 downto 0);
            curr_floor : out std_logic_vector(3 downto 0);
            door, restart : out std_logic
        );
    end component;

    component bin2seg
        port (
            clk, rst : in std_logic;
            curr_floor : in std_logic_vector(3 downto 0);
            segment : out std_logic_vector(6 downto 0);
            an : out std_logic_vector(7 downto 0);
            dp : out std_logic
        );
    end component;

end Elevator_Package;
