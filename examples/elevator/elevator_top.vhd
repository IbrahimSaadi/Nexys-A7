library IEEE;
use IEEE.STD_LOGIC_1164.ALL;
use work.Elevator_Package.ALL;

entity elevator_top is
    port (
        clk, rst, go : in std_logic;
        dest_floor : in std_logic_vector(3 downto 0);
        segment : out std_logic_vector(6 downto 0);
        an : out std_logic_vector(7 downto 0);
        dp, door : out std_logic
    );
end elevator_top;

architecture Structural of elevator_top is

    constant DEBOUNCE_CYCLES : integer := 2000000; -- 20 ms at 100 MHz
    signal tick_1hz, restart : std_logic;
    signal curr_floor : std_logic_vector(3 downto 0);

    signal go_meta, go_sync : std_logic := '0';
    signal go_stable, go_prev : std_logic := '0';
    signal go_pulse : std_logic;
    signal dest_meta, dest_sync : std_logic_vector(3 downto 0) := "0000";
    signal db_count : integer range 0 to DEBOUNCE_CYCLES-1 := 0;

begin

    -- Synchronize physical inputs and debounce the pushbutton.
    INPUTS: process (clk, rst)
    begin
        if rst = '1' then
            go_meta <= '0';
            go_sync <= '0';
            go_stable <= '0';
            go_prev <= '0';
            dest_meta <= "0000";
            dest_sync <= "0000";
            db_count <= 0;
        elsif (clk'EVENT and clk = '1') then
            go_meta <= go;
            go_sync <= go_meta;
            dest_meta <= dest_floor;
            dest_sync <= dest_meta;
            go_prev <= go_stable;

            if go_sync = go_stable then
                db_count <= 0;
            elsif db_count = DEBOUNCE_CYCLES-1 then
                db_count <= 0;
                go_stable <= go_sync;
            else
                db_count <= db_count + 1;
            end if;
        end if;
    end process;

    go_pulse <= go_stable and not go_prev;

    -- HW1-style package components and positional port maps.
    U1 : clk_div
        port map (clk, rst, restart, tick_1hz);

    U2 : fsm
        port map (clk, rst, go_pulse, tick_1hz, dest_sync,
                  curr_floor, door, restart);

    U3 : bin2seg
        port map (clk, rst, curr_floor, segment, an, dp);

end Structural;
