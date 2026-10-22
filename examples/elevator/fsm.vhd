LIBRARY IEEE;
USE IEEE.STD_LOGIC_1164.ALL;

ENTITY fsm IS
    PORT (
        clk, rst, go_pulse, tick_1hz : IN STD_LOGIC;
        dest_floor : IN STD_LOGIC_VECTOR(3 DOWNTO 0);
        curr_floor : OUT STD_LOGIC_VECTOR(3 DOWNTO 0);
        door, restart : OUT STD_LOGIC
    );
END fsm;

ARCHITECTURE Behavioral OF fsm IS
    -- VHDL reserves WAIT and OPEN as keywords.
    TYPE state IS (ST_WAIT, ST_MOVE, ST_OPEN);
    SIGNAL pr_state, nx_state : state := ST_WAIT;

    SIGNAL floor_reg : INTEGER RANGE 0 TO 15 := 0;
    SIGNAL target_reg : INTEGER RANGE 0 TO 15 := 0;
    SIGNAL requested_floor : INTEGER RANGE 0 TO 15 := 0;
    SIGNAL open_count : INTEGER RANGE 0 TO 9 := 0;
BEGIN

    -- Decode the four slide-switch bits without NUMERIC_STD.
    INPUT_DECODE: PROCESS (dest_floor)
    BEGIN
        CASE dest_floor IS
            WHEN "0000" => requested_floor <= 0;
            WHEN "0001" => requested_floor <= 1;
            WHEN "0010" => requested_floor <= 2;
            WHEN "0011" => requested_floor <= 3;
            WHEN "0100" => requested_floor <= 4;
            WHEN "0101" => requested_floor <= 5;
            WHEN "0110" => requested_floor <= 6;
            WHEN "0111" => requested_floor <= 7;
            WHEN "1000" => requested_floor <= 8;
            WHEN "1001" => requested_floor <= 9;
            WHEN "1010" => requested_floor <= 10;
            WHEN "1011" => requested_floor <= 11;
            WHEN "1100" => requested_floor <= 12;
            WHEN "1101" => requested_floor <= 13;
            WHEN "1110" => requested_floor <= 14;
            WHEN "1111" => requested_floor <= 15;
            WHEN OTHERS => requested_floor <= 0;
        END CASE;
    END PROCESS;

    -------------- Lower Section (Sequential) -----------------
    LOWER: PROCESS (clk, rst)
    BEGIN
        IF rst = '1' THEN
            pr_state <= ST_WAIT;
            floor_reg <= 0;
            target_reg <= 0;
            open_count <= 0;
        ELSIF (clk'EVENT AND clk = '1') THEN
            pr_state <= nx_state;

            CASE pr_state IS
                WHEN ST_WAIT =>
                    IF go_pulse = '1' THEN
                        target_reg <= requested_floor;
                        open_count <= 0;
                    END IF;

                WHEN ST_MOVE =>
                    IF tick_1hz = '1' THEN
                        IF floor_reg < target_reg THEN
                            floor_reg <= floor_reg + 1;
                        ELSIF floor_reg > target_reg THEN
                            floor_reg <= floor_reg - 1;
                        END IF;
                    END IF;

                WHEN ST_OPEN =>
                    IF tick_1hz = '1' THEN
                        IF open_count = 9 THEN
                            open_count <= 0;
                        ELSE
                            open_count <= open_count + 1;
                        END IF;
                    END IF;
            END CASE;
        END IF;
    END PROCESS;

    -------------- Upper Section (Combinational) --------------
    UPPER: PROCESS (pr_state, go_pulse, tick_1hz,
                   requested_floor, floor_reg, target_reg, open_count)
    BEGIN
        nx_state <= pr_state;
        restart <= '0';

        CASE pr_state IS
            WHEN ST_WAIT =>
                IF go_pulse = '1' THEN
                    restart <= '1';
                    IF requested_floor = floor_reg THEN
                        nx_state <= ST_OPEN;
                    ELSE
                        nx_state <= ST_MOVE;
                    END IF;
                END IF;

            WHEN ST_MOVE =>
                -- Further GO presses and switch changes are ignored.
                IF tick_1hz = '1' THEN
                    IF floor_reg < target_reg THEN
                        IF floor_reg + 1 = target_reg THEN
                            nx_state <= ST_OPEN;
                        END IF;
                    ELSIF floor_reg > target_reg THEN
                        IF floor_reg - 1 = target_reg THEN
                            nx_state <= ST_OPEN;
                        END IF;
                    ELSE
                        nx_state <= ST_OPEN;
                    END IF;
                END IF;

            WHEN ST_OPEN =>
                IF tick_1hz = '1' AND open_count = 9 THEN
                    nx_state <= ST_WAIT;
                END IF;
        END CASE;
    END PROCESS;

    -- Encode the current integer floor as four bits.
    OUTPUT_ENCODE: PROCESS (floor_reg)
    BEGIN
        CASE floor_reg IS
            WHEN 0  => curr_floor <= "0000";
            WHEN 1  => curr_floor <= "0001";
            WHEN 2  => curr_floor <= "0010";
            WHEN 3  => curr_floor <= "0011";
            WHEN 4  => curr_floor <= "0100";
            WHEN 5  => curr_floor <= "0101";
            WHEN 6  => curr_floor <= "0110";
            WHEN 7  => curr_floor <= "0111";
            WHEN 8  => curr_floor <= "1000";
            WHEN 9  => curr_floor <= "1001";
            WHEN 10 => curr_floor <= "1010";
            WHEN 11 => curr_floor <= "1011";
            WHEN 12 => curr_floor <= "1100";
            WHEN 13 => curr_floor <= "1101";
            WHEN 14 => curr_floor <= "1110";
            WHEN 15 => curr_floor <= "1111";
            WHEN OTHERS => curr_floor <= "0000";
        END CASE;
    END PROCESS;

    door <= '1' WHEN pr_state = ST_OPEN ELSE '0';
END Behavioral;
