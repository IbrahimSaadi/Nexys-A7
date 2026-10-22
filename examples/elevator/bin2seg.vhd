LIBRARY IEEE;
USE IEEE.STD_LOGIC_1164.ALL;

ENTITY bin2seg IS
    PORT (
        clk, rst : IN STD_LOGIC;
        curr_floor : IN STD_LOGIC_VECTOR(3 DOWNTO 0);
        segment : OUT STD_LOGIC_VECTOR(6 DOWNTO 0);
        an : OUT STD_LOGIC_VECTOR(7 DOWNTO 0);
        dp : OUT STD_LOGIC
    );
END bin2seg;

ARCHITECTURE Behavioral OF bin2seg IS
    CONSTANT SCAN_DIV : INTEGER := 50000;
    SIGNAL count : INTEGER RANGE 0 TO SCAN_DIV-1 := 0;
    SIGNAL sel : STD_LOGIC := '0';
    SIGNAL ones, tens : INTEGER RANGE 0 TO 9 := 0;
    SIGNAL digit : INTEGER RANGE 0 TO 9 := 0;
BEGIN

    -- Time-domain multiplexing: alternate AN0 / AN1.
    SCAN: PROCESS (clk, rst)
    BEGIN
        IF rst = '1' THEN
            count <= 0;
            sel <= '0';
        ELSIF (clk'EVENT AND clk = '1') THEN
            IF count = SCAN_DIV-1 THEN
                count <= 0;
                sel <= NOT sel;
            ELSE
                count <= count + 1;
            END IF;
        END IF;
    END PROCESS;

    -- Decode binary floor as two decimal digits using CASE.
    BINARY_TO_DECIMAL: PROCESS (curr_floor)
    BEGIN
        CASE curr_floor IS
            WHEN "0000" => tens <= 0; ones <= 0;
            WHEN "0001" => tens <= 0; ones <= 1;
            WHEN "0010" => tens <= 0; ones <= 2;
            WHEN "0011" => tens <= 0; ones <= 3;
            WHEN "0100" => tens <= 0; ones <= 4;
            WHEN "0101" => tens <= 0; ones <= 5;
            WHEN "0110" => tens <= 0; ones <= 6;
            WHEN "0111" => tens <= 0; ones <= 7;
            WHEN "1000" => tens <= 0; ones <= 8;
            WHEN "1001" => tens <= 0; ones <= 9;
            WHEN "1010" => tens <= 1; ones <= 0;
            WHEN "1011" => tens <= 1; ones <= 1;
            WHEN "1100" => tens <= 1; ones <= 2;
            WHEN "1101" => tens <= 1; ones <= 3;
            WHEN "1110" => tens <= 1; ones <= 4;
            WHEN "1111" => tens <= 1; ones <= 5;
            WHEN OTHERS => tens <= 0; ones <= 0;
        END CASE;
    END PROCESS;

    MUX: PROCESS (ones, tens, sel)
    BEGIN
        IF sel = '0' THEN
            an <= "11111110"; -- Ones digit (AN0)
            digit <= ones;
        ELSE
            an <= "11111101"; -- Tens digit (AN1)
            digit <= tens;
        END IF;
    END PROCESS;

    SSD: PROCESS (digit)
    BEGIN
        -- segment = gfedcba; active-low.
        CASE digit IS
            WHEN 0 => segment <= "1000000";
            WHEN 1 => segment <= "1111001";
            WHEN 2 => segment <= "0100100";
            WHEN 3 => segment <= "0110000";
            WHEN 4 => segment <= "0011001";
            WHEN 5 => segment <= "0010010";
            WHEN 6 => segment <= "0000010";
            WHEN 7 => segment <= "1111000";
            WHEN 8 => segment <= "0000000";
            WHEN 9 => segment <= "0010000";
            WHEN OTHERS => segment <= "1111111";
        END CASE;
    END PROCESS;

    dp <= '1';
END Behavioral;
