library IEEE;
use IEEE.STD_LOGIC_1164.ALL;

entity clk_div is
    port (
        clk, rst, restart : in std_logic;
        tick_1hz : out std_logic
    );
end clk_div;

architecture Behavioral of clk_div is

    constant DIVISOR : integer := 100000000; -- 100 MHz / 1 Hz
    signal count : integer range 0 to DIVISOR-1 := 0;
    signal tick : std_logic := '0';

begin

    DIV: process (clk, rst)
    begin
        if rst = '1' then
            count <= 0;
            tick <= '0';
        elsif (clk'EVENT and clk = '1') then
            tick <= '0';
            if restart = '1' then
                count <= 0;
            elsif count = DIVISOR-1 then
                count <= 0;
                tick <= '1';
            else
                count <= count + 1;
            end if;
        end if;
    end process;

    tick_1hz <= tick;

end Behavioral;
