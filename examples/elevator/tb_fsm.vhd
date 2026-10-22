library IEEE;
use IEEE.STD_LOGIC_1164.ALL;


entity tb_fsm is
end tb_fsm;

architecture Test of tb_fsm is

    type floor_codes is array (0 to 15) of std_logic_vector(3 downto 0);
    constant FLOOR_CODE : floor_codes := (
        "0000", "0001", "0010", "0011",
        "0100", "0101", "0110", "0111",
        "1000", "1001", "1010", "1011",
        "1100", "1101", "1110", "1111"
    );

    signal clk : std_logic := '0';
    signal rst : std_logic := '1';
    signal go_pulse : std_logic := '0';
    signal tick_1hz : std_logic := '0';
    signal dest_floor : std_logic_vector(3 downto 0) := "0000";
    signal curr_floor : std_logic_vector(3 downto 0);
    signal door, restart : std_logic;

begin

    clk <= not clk after 5 ns;

    UUT : entity work.fsm(Behavioral)
        port map (clk, rst, go_pulse, tick_1hz,
                  dest_floor, curr_floor, door, restart);

    TEST: process
    begin
        wait for 25 ns;
        assert curr_floor = "0000" and door = '0'
            report "Reset failure" severity failure;
        rst <= '0';

        -- Request floor 0 while at floor 0: open without moving.
        wait until falling_edge(clk);
        go_pulse <= '1';
        wait until falling_edge(clk);
        go_pulse <= '0';
        wait for 1 ns;
        assert curr_floor = "0000" and door = '1'
            report "Same-floor request failure" severity failure;

        -- Door remains open for nine ticks, closes after the tenth.
        for i in 1 to 10 loop
            wait until falling_edge(clk);
            tick_1hz <= '1';
            wait until falling_edge(clk);
            tick_1hz <= '0';
            wait for 1 ns;
            if i < 10 then
                assert door = '1'
                    report "Door closed too early" severity failure;
            else
                assert door = '0'
                    report "Door did not close at 10 ticks" severity failure;
            end if;
        end loop;

        -- Travel upward: 0 -> 3.
        dest_floor <= "0011";
        wait until falling_edge(clk);
        go_pulse <= '1';
        wait until falling_edge(clk);
        go_pulse <= '0';
        wait for 1 ns;
        assert door = '0' severity failure;

        wait until falling_edge(clk);
        tick_1hz <= '1';
        wait until falling_edge(clk);
        tick_1hz <= '0';
        wait for 1 ns;
        assert curr_floor = "0001" and door = '0'
            report "Upward movement failure at floor 1" severity failure;

        -- Try to change destination during MOVE; it must be ignored.
        dest_floor <= "1111";
        wait until falling_edge(clk);
        go_pulse <= '1';
        wait until falling_edge(clk);
        go_pulse <= '0';

        for i in 2 to 3 loop
            wait until falling_edge(clk);
            tick_1hz <= '1';
            wait until falling_edge(clk);
            tick_1hz <= '0';
            wait for 1 ns;
            assert curr_floor = FLOOR_CODE(i)
                report "Movement or destination latch failure" severity failure;
        end loop;
        assert door = '1'
            report "Door did not open at floor 3" severity failure;

        for i in 1 to 10 loop
            wait until falling_edge(clk);
            tick_1hz <= '1';
            wait until falling_edge(clk);
            tick_1hz <= '0';
        end loop;
        wait for 1 ns;
        assert door = '0' and curr_floor = "0011"
            report "Door close or floor hold failure" severity failure;

        -- Travel downward: 3 -> 0.
        dest_floor <= "0000";
        wait until falling_edge(clk);
        go_pulse <= '1';
        wait until falling_edge(clk);
        go_pulse <= '0';
        for i in 2 downto 0 loop
            wait until falling_edge(clk);
            tick_1hz <= '1';
            wait until falling_edge(clk);
            tick_1hz <= '0';
            wait for 1 ns;
            assert curr_floor = FLOOR_CODE(i)
                report "Downward movement failure" severity failure;
        end loop;
        assert door = '1'
            report "Door failed to open after downward travel" severity failure;

        for i in 1 to 10 loop
            wait until falling_edge(clk);
            tick_1hz <= '1';
            wait until falling_edge(clk);
            tick_1hz <= '0';
        end loop;
        wait for 1 ns;
        assert door = '0' severity failure;

        -- Travel through all floors: 0 -> 15, with no overflow.
        dest_floor <= "1111";
        wait until falling_edge(clk);
        go_pulse <= '1';
        wait until falling_edge(clk);
        go_pulse <= '0';
        for i in 1 to 15 loop
            wait until falling_edge(clk);
            tick_1hz <= '1';
            wait until falling_edge(clk);
            tick_1hz <= '0';
            wait for 1 ns;
            assert curr_floor = FLOOR_CODE(i)
                report "Wrong floor on full upward travel" severity failure;
        end loop;
        assert door = '1' severity failure;

        report "ALL FSM TESTS PASSED" severity note;
        wait;
    end process;

end Test;
